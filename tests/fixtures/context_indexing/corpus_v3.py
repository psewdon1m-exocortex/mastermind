"""Fresh acceptance domains after paragraph-level conflict and counter-evidence fixes."""
import importlib.util
from pathlib import Path


def dataset():
    spec = importlib.util.spec_from_file_location("previous_corpus", Path(__file__).with_name("corpus_v2.py"))
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    result = previous.dataset()
    for case in result["cases"]:
        if case["split"] == "test":
            case["split"] = "development"
    topics = [
        ("Physics", "Electromagnetic induction", "Electromagnetic induction generates an electromotive force when magnetic flux changes through a circuit.", "Электромагнитная индукция создаёт электродвижущую силу при изменении магнитного потока через контур.", "Moving a magnet through a wire coil produces a voltage because the magnetic flux changes.", "Движение магнита через катушку создаёт напряжение из-за изменения магнитного потока."),
        ("Physics", "Mechanical resonance", "Mechanical resonance amplifies oscillation when a driving force matches the natural frequency of a system.", "Механический резонанс усиливает колебания, когда частота внешней силы совпадает с собственной частотой системы.", "A periodic driving force causes a large oscillation at the system's natural frequency.", "Периодическая внешняя сила вызывает большие колебания на собственной частоте системы."),
        ("Physics", "Wave diffraction", "Wave diffraction spreads a wave around obstacles and through openings comparable with its wavelength.", "Дифракция волн означает огибание препятствий и расширение волны после отверстия, сравнимого с длиной волны.", "Light spreads after passing through a narrow slit whose width is comparable to its wavelength.", "Свет расширяется после узкой щели, ширина которой сравнима с длиной волны."),
        ("Physics", "Radioactive decay", "Radioactive decay transforms unstable atomic nuclei through spontaneous radiation emission; half-life describes its rate.", "Радиоактивный распад превращает нестабильные атомные ядра при спонтанном излучении; период полураспада описывает скорость.", "Unstable nuclei spontaneously emit radiation and half the sample transforms during one half-life.", "Нестабильные ядра самопроизвольно излучают, и половина образца превращается за период полураспада."),
        ("Physics", "Thermal conduction", "Thermal conduction transfers heat through matter by microscopic interactions without bulk motion of the material.", "Теплопроводность переносит тепло через вещество микроскопическими взаимодействиями без перемещения вещества целиком.", "The hot end of a metal rod warms its cooler end without any bulk flow of metal.", "Горячий конец металлического стержня нагревает холодный без перемещения металла целиком."),
        ("History", "Agricultural settlement", "Early agricultural settlement replaced some mobile foraging with crop cultivation, animal domestication and permanent villages.", "Ранние земледельческие поселения сменили часть кочевого собирательства выращиванием культур, одомашниванием животных и постоянными деревнями.", "Early communities began cultivating crops and keeping domesticated animals in permanent villages.", "Ранние общины начали выращивать культуры и держать домашних животных в постоянных деревнях."),
        ("History", "Movable type printing", "Movable type printing reuses individual characters to reproduce texts and accelerates the circulation of books.", "Печать подвижными литерами повторно использует отдельные знаки для воспроизведения текстов и ускоряет распространение книг.", "Reusable individual metal letters allowed printers to reproduce many copies of a book.", "Многоразовые отдельные металлические буквы позволили печатникам выпускать множество копий книги."),
        ("History", "Industrial revolution", "The industrial revolution expanded mechanized factory production, steam power and urban industrial employment.", "Промышленная революция расширила механизированное фабричное производство, использование пара и городскую промышленную занятость.", "Steam engines and mechanized factories changed production and drew workers into industrial cities.", "Паровые машины и механизированные фабрики изменили производство и привлекли рабочих в промышленные города."),
        ("History", "Medieval craft guilds", "Medieval craft guilds regulated apprenticeships, workmanship and the organization of skilled trades in towns.", "Средневековые ремесленные цехи регулировали ученичество, качество изделий и организацию ремёсел в городах.", "Urban associations of medieval artisans regulated apprenticeship and standards of workmanship.", "Городские объединения средневековых ремесленников регулировали ученичество и стандарты качества изделий."),
        ("History", "Maritime exploration", "Maritime exploration developed long-distance navigation, mapped sea routes and connected previously separate regions.", "Морские исследования развивали дальнюю навигацию, картографировали морские пути и соединяли ранее разобщённые регионы.", "Long ocean voyages mapped new sea routes and connected distant regions through improved navigation.", "Дальние океанские плавания картографировали новые морские пути и соединяли удалённые регионы благодаря развитию навигации."),
    ]
    result["notes"]["root.md"] += "\n[[Physics]]\n[[History]]"
    for index, (domain, title, en, ru, implicit, implicit_ru) in enumerate(topics, 40):
        target = "Branches/"+title+".md"
        parent = "Branches/"+domain+".md"
        result["notes"].setdefault(parent, "#main\n")
        result["notes"][parent] += "[["+title+"]]\n"
        result["notes"][target] = "#key\n"+title+"\n[[Evidence "+str(index)+"]]"
        result["notes"]["Notes/Evidence "+str(index)+".md"] = en+"\n"+ru+"\n[["+title+"]]"
        samples = [implicit, implicit_ru, title+". "+implicit, title+". "+implicit_ru,
                   "Research on "+title+": "+implicit, "Исследование "+title+": "+implicit_ru,
                   "Research question: "+implicit+"\nSubject area: "+title,
                   "Подробное описание темы "+title+"\n"+("This document discusses the source and its explanation. "*40)+implicit_ru]
        for variant, source in enumerate(samples):
            result["cases"].append({"id": f"{index:02d}-{variant}", "group": domain, "split": "test", "source": source,
                "acceptable": [target], "must_pool": False, "reason": "Source evidence belongs to this uniquely reachable key."})
        other = topics[((index-40)+5) % 10]
        result["cases"].append({"id": f"{index:02d}-mixed", "group": domain, "split": "test", "source": en+"\nIndependently, "+other[2],
            "acceptable": [], "must_pool": True, "reason": "Two unrelated disciplines have independent evidence."})
        result["cases"].append({"id": f"{index:02d}-new", "group": domain, "split": "test",
            "source": "A record of decorative napkin folding customs. No information about "+title+" is included.",
            "acceptable": [], "must_pool": True, "reason": "The actual subject is absent from this graph; the title mention denies evidence."})
    result["schema"] = "context-indexing.corpus.v3"
    return result
