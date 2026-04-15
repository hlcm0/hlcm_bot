from __future__ import annotations


def get_grade_factor(score: int) -> float:
    if score >= 9900000:
        return 1.05
    if score >= 9800000:
        return 1.02
    if score >= 9700000:
        return 1.00
    if score >= 9500000:
        return 0.97
    if score >= 9300000:
        return 0.94
    if score >= 9000000:
        return 0.91
    if score >= 8700000:
        return 0.88
    if score >= 7500000:
        return 0.85
    if score >= 6500000:
        return 0.82
    return 0.80


def calc_vf(level: float, score: int, grade_factor: float, clear_factor: float) -> float:
    return int(level * (score / 10000000.0) * grade_factor * clear_factor * 20) / 20


def normalize_score(raw_score: str | int) -> int:
    if isinstance(raw_score, str):
        if raw_score.lower() == "puc":
            return 10000000
        score = int(raw_score)
    else:
        score = raw_score

    if score <= 1000:
        score *= 10000
    return score


def calculate_vf_message(level: float, raw_score: str | int) -> str:
    try:
        score = normalize_score(raw_score)

        if level < 1 or level > 21:
            raise ValueError("等级应当在1-21之间")
        if score < 0 or score > 10000000:
            raise ValueError("分数应当在0-10000000之间")
    except ValueError as e:
        return str(e)

    grade_factor = get_grade_factor(score)
    puc_vf = calc_vf(level, score, grade_factor, 1.10)
    uc_vf = calc_vf(level, score, grade_factor, 1.06)
    mc_vf = calc_vf(level, score, grade_factor, 1.04)
    hc_vf = calc_vf(level, score, grade_factor, 1.02)
    ec_vf = calc_vf(level, score, grade_factor, 1.00)
    tc_vf = calc_vf(level, score, grade_factor, 0.50)

    if score == 10000000:
        return f"PUC: {puc_vf}"
    if score >= 5000000:
        return f"UC: {uc_vf}\nMAXXIVE: {mc_vf}\nHARD: {hc_vf}\nEASY: {ec_vf}\nCRASH: {tc_vf}"
    return f"MAXXIVE: {mc_vf}\nHARD: {hc_vf}\nEASY: {ec_vf}\nCRASH: {tc_vf}"
