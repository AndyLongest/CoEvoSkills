import math

def poly4(a, b, c, d, e, x):
    return a*x**4 + b*x**3 + c*x**2 + d*x + e

def dots_coefficient_men(bw):
    bw = max(40.0, min(210.0, bw))
    return 500.0 / poly4(-0.0000010930, 0.0007391293, -0.1918759221, 24.0900756, -307.75076, bw)

def dots_coefficient_women(bw):
    bw = max(40.0, min(150.0, bw))
    return 500.0 / poly4(-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288, bw)

def dots_coefficient(sex, bw):
    if sex in ["M", "Mx"]:
        return dots_coefficient_men(bw)
    return dots_coefficient_women(bw)

def dots_score(sex, bw, total):
    if not bw or not total:
        return 0.0
    return dots_coefficient(sex, bw) * total
