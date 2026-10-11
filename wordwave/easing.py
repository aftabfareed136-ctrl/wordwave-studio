"""AE-style easing functions. All take x in [0,1] and return eased y in ~[0,1].

Back / elastic / bounce intentionally overshoot like After Effects'
Easy Ease + expression-driven overshoot presets.
"""
import math


def clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def linear(x: float) -> float:
    return clamp01(x)


def ease_in_quad(x: float) -> float:
    x = clamp01(x)
    return x * x


def ease_out_quad(x: float) -> float:
    x = clamp01(x)
    return 1.0 - (1.0 - x) * (1.0 - x)


def ease_in_out_quad(x: float) -> float:
    x = clamp01(x)
    return 2 * x * x if x < 0.5 else 1.0 - ((-2 * x + 2) ** 2) / 2


def ease_out_cubic(x: float) -> float:
    x = clamp01(x)
    return 1.0 - (1.0 - x) ** 3


def ease_in_out_cubic(x: float) -> float:
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1.0 - ((-2 * x + 2) ** 3) / 2


def ease_out_quart(x: float) -> float:
    x = clamp01(x)
    return 1.0 - (1.0 - x) ** 4


def ease_out_expo(x: float) -> float:
    x = clamp01(x)
    return 1.0 if x >= 1.0 else 1.0 - 2.0 ** (-10 * x)


def ease_out_back(x: float, s: float = 1.70158) -> float:
    """Overshoot ease — the classic 'pop' used by kinetic typography."""
    x = clamp01(x)
    c3 = s + 1.0
    return 1.0 + c3 * (x - 1.0) ** 3 + s * (x - 1.0) ** 2


def ease_out_elastic(x: float) -> float:
    x = clamp01(x)
    if x == 0.0 or x == 1.0:
        return x
    return 2.0 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi / 3)) + 1.0


def ease_out_bounce(x: float) -> float:
    x = clamp01(x)
    n1, d1 = 7.5625, 2.75
    if x < 1 / d1:
        return n1 * x * x
    if x < 2 / d1:
        x -= 1.5 / d1
        return n1 * x * x + 0.75
    if x < 2.5 / d1:
        x -= 2.25 / d1
        return n1 * x * x + 0.9375
    x -= 2.625 / d1
    return n1 * x * x + 0.984375


def spring(x: float, stiffness: float = 170.0, damping: float = 14.0) -> float:
    """Under-damped spring towards 1 — feels physical, like AE's inertia."""
    x = clamp01(x)
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    w = math.sqrt(max(stiffness, 1e-6))
    z = damping / (2 * w)
    t = x * 1.2  # settle a touch before 1.0
    if z < 1.0:
        wd = w * math.sqrt(1 - z * z)
        return 1.0 - math.exp(-z * w * t) * (math.cos(wd * t) + z * math.sin(wd * t) / math.sqrt(1 - z * z))
    return 1.0 - math.exp(-w * t) * (1 + w * t)


EASES = {
    "linear": linear,
    "in": ease_in_quad,
    "out": ease_out_quad,
    "in-out": ease_in_out_quad,
    "out-cubic": ease_out_cubic,
    "in-out-cubic": ease_in_out_cubic,
    "out-quart": ease_out_quart,
    "out-expo": ease_out_expo,
    "back": ease_out_back,      # pop / overshoot
    "elastic": ease_out_elastic,
    "bounce": ease_out_bounce,
    "spring": spring,
}


def get(name: str):
    try:
        return EASES[name]
    except KeyError:
        raise ValueError(f"Unknown easing '{name}'. Available: {sorted(EASES)}")
