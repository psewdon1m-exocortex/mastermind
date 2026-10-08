"""Capability-scoped note editor; no owner APIs, browser persistence or resolver."""

from pathlib import Path

STYLE = """*{box-sizing:border-box;scrollbar-width:none}*::-webkit-scrollbar{display:none;width:0;height:0}:root{--accent:#00a8ff}body{margin:0;background:#000;color:#fff;font:14px/1.6 Consolas,'Cascadia Mono',monospace}
header{min-height:123px;border-bottom:1px solid #ccc;padding:20px 30px;display:flex;align-items:center}h1{font:700 clamp(40px,4.2vw,80px)/1 'Space Grotesk','Segoe UI',sans-serif;color:var(--accent);margin:0;overflow-wrap:anywhere}h2{font-size:22px;color:var(--accent);margin:0 0 16px}
main{padding:20px 30px 60px}p{overflow-wrap:anywhere}button,input,textarea{font:inherit;color:inherit;background:#000;border:1px solid #ccc;border-radius:0}button,input{min-height:40px;padding:8px 12px}button{cursor:pointer}button:hover:enabled{background:#111;border-color:var(--accent)}:focus-visible{outline:1px solid var(--accent);outline-offset:3px}button:disabled{opacity:.45;cursor:default}button:active:enabled{transform:scale(.985)}
.gate{min-height:100dvh;display:grid;place-items:center;padding:24px}.gate-group{width:255px;max-width:100%}.gate-panel{border:1px solid #fff;padding:15px;display:grid;gap:10px}.gate-panel p{color:var(--accent);margin:0 0 10px}.gate-panel input{width:100%;min-width:0}.gate-panel button{color:var(--accent);border-color:var(--accent)}.gate-panel .error{color:#f83d3d;margin:0}.error:empty{display:none}.reach{margin-top:16px;border:1px solid #ccc;color:#ccc;padding:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:50px;font-size:13px}.reach i{display:inline-block;width:19px;height:19px;background:currentColor}.reach[data-state=ok]{color:#62ff8c;border-color:currentColor}.reach[data-state=error]{color:#f83d3d;border-color:currentColor}
#surface{overflow-wrap:anywhere;min-height:160px}#surface>h1:first-child{font-size:32px}.note-field{display:block;border:0;border-left:1px solid transparent;padding:0 6px;margin:0;width:100%;min-height:26px;resize:none;overflow:hidden;background:#000;line-height:1.6;outline:0;white-space:pre-wrap;tab-size:4}.note-field:focus{border-left-color:var(--accent)}.protected{border-left:1px solid #ccc;color:#ccc;padding:6px 12px;margin:8px 0;font-size:12px}pre{overflow:auto;white-space:pre-wrap}
#notice{color:#ccc;min-height:24px;font-size:12px;margin:8px 0 0}#notice[data-error=true]{color:#f83d3d}#conflict{border:1px solid #f83d3d;padding:20px;margin:24px 0}.draft-field{width:100%;min-height:100px;padding:12px;resize:vertical;margin-bottom:12px}.commands{display:flex;justify-content:flex-end;gap:12px;margin-top:16px}.commands button{border-color:var(--accent);color:var(--accent)}#retry{margin-top:16px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}[hidden]{display:none!important}
@media(max-width:720px){header{padding:20px;min-height:96px}main{padding:16px 20px 40px}h1{font-size:40px}#conflict{padding:14px}}@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

SCRIPT = (Path(__file__).parent / "web/shared-public.js").read_text(encoding="utf-8")


def legacy_html(nonce, accent="#00A8FF", token=""):
    style = ('@font-face{font-family:"Space Grotesk";font-weight:700;font-display:swap;'
             'src:url("/s/' + token + '/font.woff2") format("woff2")}\n' + STYLE).replace("#00a8ff", accent)
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Shared note · Mastermind</title><style nonce="' + nonce + '">' + style + '</style><body data-view="legacy">'
            '<div class="gate" id="gate"><div class="gate-group"><form id="unlockForm" class="gate-panel">'
            '<p>Please enter<br>shared link password:</p><label id="passwordLabel"><span class="sr-only">Share password</span>'
            '<input id="password" type="password" autocomplete="current-password" placeholder="Password…"></label>'
            '<button id="unlock">Enter</button><p class="error" id="gateError" role="alert"></p></form>'
            '<div class="reach" id="reach" role="status"><span id="reachText">Checking service</span><i aria-hidden="true"></i></div></div></div>'
            '<div id="workspace" hidden><header><h1 id="title"></h1></header><main>'
            '<article id="surface" aria-label="Shared note"></article><p id="notice" role="status" aria-live="polite"></p>'
            '<button id="retry" hidden>Retry save</button><section id="conflict" hidden><h2>Unsaved Markdown</h2>'
            '<p>The editor above contains the current note. Your previous draft is retained here. Copy the changes you want to keep into the editor, then save the merged version.</p>'
            '<div id="draft"></div><div class="commands"><button id="saveMerged">Save merged changes</button></div></section></main></div>'
            '<script nonce="' + nonce + '">' + SCRIPT + '</script></body></html>')


PUBLIC_STYLE = (Path(__file__).parent / "web/shared-public.css").read_text(encoding="utf-8")


def page_html(nonce, accent="#00A8FF", token="", *, legacy=False, unavailable=False):
    """Two presentations, one capability-scoped controller and authorization flow."""
    if legacy and not unavailable:
        return legacy_html(nonce, accent, token)
    asset = "/s/" + token
    fonts = "" if unavailable else (
        '@font-face{font-family:"Space Grotesk";font-weight:400;font-display:swap;'
        'src:url("' + asset + '/font-regular.woff2")} '
        '@font-face{font-family:"Space Grotesk";font-weight:700;font-display:swap;'
        'src:url("' + asset + '/font.woff2")}')
    brand = ('<div class="brand">' + ('' if unavailable else
             '<img src="' + asset + '/brand.png" alt="" width="36" height="36">') + 'Mastermind</div>')
    head = ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Shared note · Mastermind</title><style nonce="' + nonce + '">' + fonts +
            (STYLE if legacy else PUBLIC_STYLE) + '</style><body class="' +
            ('legacy-share' if legacy else 'public-share') + '" data-view="' +
            ('legacy' if legacy else 'public') + '">')
    if unavailable:
        return (head + '<main class="gate unavailable"><div class="gate-group">' + brand +
                '<h1>Link unavailable</h1><p>This shared link is not available. '
                'Ask the sender for a new link.</p></div></main></body></html>')
    return (head +
            '<div id="loading" class="gate" role="status">Opening shared note…</div>'
            '<div class="gate" id="gate" hidden><div class="gate-group">' + brand +
            '<form id="unlockForm" class="gate-panel">'
            '<div class="lock-symbol" aria-hidden="true"></div><p class="eyebrow">Private shared link</p>'
            '<h1>This link is protected</h1><p class="explanation">Enter the password provided by the sender to open this note.</p>'
            '<label id="passwordLabel">Password<input id="password" type="password" autocomplete="current-password" '
            'aria-describedby="gateError" placeholder="Enter password"></label>'
            '<button id="unlock">Continue</button><p class="error" id="gateError" role="alert"></p>'
            '<div class="reach" id="reach" role="status"><span id="reachText"></span></div></form>'
            '<p class="attribution">Shared via Mastermind</p></div></div>'
            '<div id="workspace" hidden><header class="topbar">' + brand +
            '<div class="access-facts"><span id="access"></span><span id="expiry"></span></div></header><main>'
            '<p class="eyebrow">Shared note</p><h1 id="title"></h1>'
            '<article id="surface" aria-label="Shared note"></article><p id="notice" role="status" aria-live="polite"></p>'
            '<button id="retry" hidden>Retry save</button><section id="conflict" hidden><h2>Unsaved Markdown</h2>'
            '<p>The editor above contains the current note. Your previous draft is retained here. Copy the changes '
            'you want to keep into the editor, then save the merged version.</p><div id="draft"></div>'
            '<div class="commands"><button id="saveMerged">Save merged changes</button></div></section>'
            '<details><summary>About access</summary><p>This link provides access only to the shared note. '
            'Hidden content and linked resources are not shared. The sender can revoke access or change its permissions.</p>'
            '<p id="editingHelp"></p><p>View only prevents editing through this link. Content displayed in your '
            'browser can still be copied.</p></details><footer class="attribution">Shared via Mastermind</footer>'
            '</main></div><script nonce="' + nonce + '">' + SCRIPT + '</script></body></html>')
