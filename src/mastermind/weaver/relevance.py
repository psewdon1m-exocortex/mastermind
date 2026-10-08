"""Task-specific acceptance; scores rank evidence and are never probabilities.

These thresholds are evaluated against the pinned E5 corpus. Placement keeps
its independent, model-bound calibration in policy.py.
"""
VERSION = 'weaver.relevance.v1'


def judge(task, *, lexical, common, title, named, descriptive, vector, contrast, verified, best, background_available=True):
    topical = lexical >= .14 and common >= 2 or title >= .75 and named
    if task == 'knowledge_lookup':
        if named and title >= .75:
            return 'strong', 'EXPLICIT_NAME'
        if topical:
            return 'strong', 'TOPICAL_OVERLAP'
        if verified and descriptive and not background_available and vector >= .80:
            return 'tentative', 'NO_BACKGROUND_SAMPLE'
        if verified and descriptive and vector >= .80 and contrast >= .055:
            return 'strong', 'VERIFIED_SEMANTIC'
        # Bilingual paraphrases often sit below .80. Keep a bounded, relatively
        # distinct verified candidate and expose uncertainty to the consumer.
        if verified and descriptive and vector >= .76 and contrast >= .035 and vector >= best-.04:
            return 'tentative', 'VERIFIED_LOW_MARGIN'
    else:
        if named and title >= .75:
            return 'strong', 'EXPLICIT_NAME'
        if verified:
            if descriptive and not background_available and vector >= .90:
                return 'strong', 'HIGH_ABSOLUTE_SIMILARITY'
            if descriptive and vector >= .83 and contrast >= .04:
                return 'strong', 'VERIFIED_SEMANTIC'
            if lexical >= .20 and common >= 2 and vector >= .80 and contrast >= .025:
                return 'strong', 'CORROBORATED_TOPIC'
        elif topical:
            return 'strong', 'LEXICAL_ONLY'
    return 'rejected', 'WEAK_TOPIC_EVIDENCE'
