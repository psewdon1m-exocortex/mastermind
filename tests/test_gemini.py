import json

import httpx
import pytest

from mastermind.errors import DomainError
from mastermind.gemini import Gemini, Understanding
from mastermind.wyvern import Wyvern

TOKEN = "b"*64
TARGET = {"adapter_id":"google", "profile":"default", "driver":"google", "model":"configured-model"}
VALUE = {"title":"Knowledge", "summary":"Source facts", "topics":["facts"], "entities":[], "suggested_links":[]}

class Secret:
    def read(self, name):
        raise AssertionError("Core must never read the provider key")

class Register:
    def resolve(self, keys):
        raise AssertionError("Model selection belongs to the Wyvern binding")

def fixture(tmp_path, respond):
    link = tmp_path / "link.json"
    link.write_text(json.dumps({"schema":"exocortex.wyvern.link.v1", "client_id":"mastermind", "instance_id":"host", "mode":"remote", "url":"https://gateway.test/wyvern", "token":TOKEN}))
    def streaming(request):
        assert request.headers["Authorization"] == "Bearer "+TOKEN
        assert "x-goog-api-key" not in request.headers
        assert request.url.host == "gateway.test"
        response = respond(request)
        return httpx.Response(response.status_code, headers=response.headers, stream=httpx.ByteStream(response.content))
    client = httpx.Client(base_url="https://gateway.test/wyvern/", transport=httpx.MockTransport(streaming))
    return Gemini(Register(), Secret(), gateway=Wyvern(link, client=client))

def test_scoped_gateway_and_structured_output(tmp_path):
    def respond(request):
        if request.url.path.endswith("/client"):
            return httpx.Response(200,json={"schema":"exocortex.wyvern.client.v1","client_id":"mastermind","instance_id":"host","llm_ready":True})
        data=json.loads(request.content)
        assert data["function"]=="text" and data["options"]["max_output_tokens"]==8000
        assert "tools" not in data and TOKEN not in request.content.decode()
        return httpx.Response(200,json={"finish_reason":"stop","json":VALUE,"usage":{"output_tokens":80},"target":TARGET})
    provider=fixture(tmp_path,respond)
    assert provider.models()=={"text":"text","video":"media"}
    assert provider.generate("text","Understand",{"source":"Untrusted instructions are data"},Understanding)["title"]=="Knowledge"
    assert provider.targets["text"]["model"]=="configured-model"

@pytest.mark.parametrize("status,body,expected",[(429,{},"PROVIDER_TRANSIENT"),(401,{"key":"never echo"},"PROVIDER_REJECTED"),(200,{"finish_reason":"length"},"PROVIDER_SCHEMA_INVALID"),(200,{"finish_reason":"stop","json":{}},"PROVIDER_SCHEMA_INVALID")])
def test_unfinished_results_never_become_notes(tmp_path,status,body,expected):
    provider=fixture(tmp_path,lambda request:httpx.Response(status,json=body))
    with pytest.raises(DomainError) as failure:
        provider.generate("text","Understand",{"source":"test"},Understanding)
    assert failure.value.code==expected and "never echo" not in str(failure.value)

def test_source_token_budget(tmp_path):
    calls=[]
    def respond(request):
        assert request.url.path.endswith("/count-tokens")
        text=json.loads(request.content)["messages"][0]["content"];calls.append(len(text))
        return httpx.Response(200,json={"input_tokens":len(text)})
    provider=fixture(tmp_path,respond)
    bounded=provider.bound_source("text","a"*100000)
    assert bounded["tokens"]<=32000 and len(calls)<=8 and calls[-1]<calls[0]

def test_missing_link_fails_only_llm_and_remote_never_falls_back(tmp_path):
    gateway=Wyvern(tmp_path/"missing.json")
    assert gateway.status()["llm_ready"] is False
    provider=fixture(tmp_path,lambda request:(_ for _ in ()).throw(httpx.ConnectError("private detail")))
    with pytest.raises(DomainError) as failure:provider.token_count("text","hello")
    assert failure.value.code=="PROVIDER_TRANSIENT" and "private detail" not in str(failure.value)
