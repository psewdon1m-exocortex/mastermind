"""Replacement held-out domains after the first baseline exposed insufficient implicit-topic coverage.

The original test domains become development data. New test labels must never
be used to tune the frozen operating point; all 400 cases retain grouped splits.
"""
import importlib.util
from pathlib import Path


def dataset():
    spec = importlib.util.spec_from_file_location("original_corpus", Path(__file__).with_name("corpus.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TOPICS = [(domain, "development" if split == "test" else split, *rest)
                     for domain, split, *rest in module.TOPICS]
    module.TOPICS.extend([
        ("Chemistry", "test", "Buffer solutions", "Buffer solutions resist pH changes through a weak acid and its conjugate base.", "Буферные растворы сопротивляются изменению pH благодаря слабой кислоте и сопряжённому основанию.", "Why does adding a little acid to a weak acid and conjugate base mixture barely change its pH?", "Почему смесь слабой кислоты и сопряжённого основания сохраняет pH при добавлении небольшого количества кислоты?"),
        ("Chemistry", "test", "Chemical equilibrium", "At chemical equilibrium the forward and reverse reaction rates are equal and concentrations remain constant.", "В химическом равновесии скорости прямой и обратной реакций равны, а концентрации постоянны.", "A reversible reaction continues in both directions at equal rates while concentrations stay constant.", "Обратимая реакция продолжается в обе стороны с одинаковой скоростью при постоянных концентрациях."),
        ("Chemistry", "test", "Redox reactions", "Oxidation loses electrons and reduction gains electrons; electron transfer couples both processes.", "Окисление отдаёт электроны, восстановление принимает; оба процесса связаны переносом электронов.", "One reactant gives up electrons while another accepts them.", "Один реагент отдаёт электроны, а другой принимает их."),
        ("Chemistry", "test", "Crystal lattice", "A crystal lattice repeats an ordered arrangement of atoms, ions or molecules through space.", "Кристаллическая решётка повторяет упорядоченное расположение атомов, ионов или молекул в пространстве.", "An ordered solid repeats the same atomic arrangement in three dimensions.", "Упорядоченное твёрдое тело повторяет одно расположение атомов в трёх измерениях."),
        ("Chemistry", "test", "Polymerization", "Polymerization joins monomers into long molecular chains through addition or condensation reactions.", "Полимеризация соединяет мономеры в длинные молекулярные цепи через реакции присоединения или конденсации.", "Small monomer molecules join into long chains to form a macromolecule.", "Маленькие молекулы мономера соединяются в длинную цепь макромолекулы."),
        ("Linguistics", "test", "Phonemes", "Phonemes are contrastive speech sound units; minimal pairs distinguish word meanings through one sound.", "Фонемы различают значения слов; минимальные пары отличаются одним звуком речи.", "Two words differ in only one speech sound and that difference changes their meaning.", "Два слова различаются одним звуком, и эта разница меняет значение."),
        ("Linguistics", "test", "Morphology", "Morphology studies word structure, morphemes, inflection and derivation.", "Морфология изучает структуру слова, морфемы, словоизменение и словообразование.", "Analyze how a stem combines with prefixes and suffixes to form a word.", "Разобрать, как основа соединяется с приставками и суффиксами для образования слова."),
        ("Linguistics", "test", "Syntax", "Syntax studies sentence structure, grammatical relations and the arrangement of phrases.", "Синтаксис изучает структуру предложения, грамматические отношения и организацию словосочетаний.", "How does the arrangement of phrases determine grammatical relations in a sentence?", "Как расположение словосочетаний определяет грамматические отношения в предложении?"),
        ("Linguistics", "test", "Semantic ambiguity", "Semantic ambiguity occurs when a word or sentence permits multiple interpretations; context can disambiguate meaning.", "Семантическая неоднозначность возникает при нескольких толкованиях слова или предложения; контекст помогает выбрать значение.", "A sentence has several possible meanings until its surrounding context resolves the interpretation.", "Предложение имеет несколько возможных смыслов, пока окружающий контекст не уточнит толкование."),
        ("Linguistics", "test", "Language acquisition", "Language acquisition develops vocabulary and grammar through exposure and interaction, especially during childhood.", "Усвоение языка развивает словарь и грамматику через общение и восприятие речи, особенно в детстве.", "A child learns vocabulary and grammatical patterns through conversation and exposure to speech.", "Ребёнок осваивает словарь и грамматические закономерности через разговоры и восприятие речи."),
    ])
    result = module.dataset()
    result["schema"] = "context-indexing.corpus.v2"
    for case in result["cases"]:
        if case["split"] == "test" and case["id"].endswith("-new"):
            case["source"] = case["source"].replace("basket weaving traditions", "decorative gift wrapping customs")
    return result
