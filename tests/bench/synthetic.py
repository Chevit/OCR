"""Generate a small synthetic benchmark set: rendered Ukrainian/English text,
degraded like real uploads (scans, messenger-compressed images, photos with
shadows, tilt and keystone, dark-theme screenshots). Only a smoke set until
real anonymized documents land in tests/bench/images/; results on it say
little about real pages.

    python -m tests.bench.synthetic tests/bench/synthetic
"""
import io
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONTS = {
    "arial": ["/System/Library/Fonts/Supplemental/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "times": ["/System/Library/Fonts/Supplemental/Times New Roman.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
    "courier": ["/System/Library/Fonts/Supplemental/Courier New.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
}

TEXTS = [
    "Виписка з медичної карти стаціонарного хворого № 4127. Пацієнт перебував "
    "на лікуванні з 03.02.2024 по 14.02.2024. Діагноз основний: J45.0 "
    "бронхіальна астма, переважно алергічна, середнього ступеня тяжкості. "
    "Супутній: I10 есенціальна гіпертензія. Призначено: Salbutamol 100 мкг "
    "по потребі, Budesonide 200 мкг двічі на день, контроль тиску щоранку.",
    "Скарги на біль в епігастрії після їжі, печію, нудоту протягом трьох "
    "тижнів. Об'єктивно: живіт м'який, болючий при пальпації в "
    "епігастральній ділянці. ФГДС від 21.11.2023: ознаки гастриту. "
    "Діагноз: K29.7 гастрит неуточнений. Omeprazole 20 мг двічі на день "
    "14 днів, дієта, повторний огляд через місяць.",
    "Загальний аналіз крові від 07.03.2024: гемоглобін 128 г/л, еритроцити "
    "4,2 Т/л, лейкоцити 9,8 Г/л, тромбоцити 245 Г/л, ШОЕ 18 мм/год. "
    "Глюкоза крові натще 5,9 ммоль/л. Креатинін 88 мкмоль/л. Рекомендовано "
    "консультацію ендокринолога та контроль глікованого гемоглобіну HbA1c.",
    "Пацієнтка 1967 р. н. звернулася зі скаргами на головний біль, "
    "запаморочення та підвищення артеріального тиску до 170/100 мм рт. ст. "
    "Анамнез: гіпертонічна хвороба понад 10 років. Діагноз: I11.9 "
    "гіпертензивна хвороба серця без серцевої недостатності. Amlodipine "
    "5 мг один раз на добу, Lisinopril 10 мг вранці.",
    "Направлення на консультацію до невролога. Діагноз попередній: M54.5 "
    "біль у нижній частині спини. Тривалість захворювання близько двох "
    "місяців, посилення після фізичного навантаження. МРТ поперекового "
    "відділу хребта від 15.01.2024 додається. Лікар загальної практики "
    "Коваленко О. П., тел. 044 235 18 70.",
    "Рецепт: Amoxicillin 500 мг по одній капсулі тричі на добу протягом "
    "7 днів. Ibuprofen 400 мг при температурі вище 38,5 °C, не більше "
    "трьох разів на добу. Діагноз: J02.9 гострий фарингіт неуточнений. "
    "Повторний огляд 22.04.2024 або раніше при погіршенні стану.",
    "Ехокардіографія: ліві відділи серця не розширені, фракція викиду 62 %, "
    "зон гіпокінезу не виявлено. Клапани без патології, тиск у легеневій "
    "артерії 24 мм рт. ст. Висновок: варіант норми. Рекомендовано ЕКГ "
    "контроль через 6 місяців, Holter-моніторинг за потреби.",
    "Довідка видана для пред'явлення за місцем роботи. Пацієнт був "
    "непрацездатний з 10.10.2024 по 17.10.2024 у зв'язку із захворюванням "
    "J06.9 гостра інфекція верхніх дихальних шляхів. До роботи з "
    "18.10.2024. Підпис лікаря, печатка закладу охорони здоров'я.",
]


def font_path(name):
    path = next((p for p in FONTS[name] if os.path.exists(p)), None)
    if not path:
        sys.exit(f"no font for {name}: tried {FONTS[name]}")
    return path


def render(text, font_name, size, width=2480, fg=0, bg=255, margin=180):
    """Text wrapped to the page width; returns (image, ground-truth lines)."""
    font = ImageFont.truetype(font_path(font_name), size)
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.getlength(trial) > width - 2 * margin and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    pitch = int(size * 1.6)
    img = Image.new("L", (width, 2 * margin + pitch * len(lines)), bg)
    draw = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        draw.text((margin, margin + i * pitch), l, fill=fg, font=font)
    return img, lines


def uneven_light(img, rng):
    """Light falling off across the page plus a soft shadow blob, like a
    phone photo taken under a desk lamp."""
    w, h = img.size
    light = Image.linear_gradient("L").resize((w, h)).rotate(rng.choice([0, 90, 180, 270]))
    light = light.point(lambda v: 110 + v * 145 // 255)  # 0.43 .. 1.0
    shadow = Image.new("L", (w, h), 255)
    ImageDraw.Draw(shadow).ellipse(
        (w * rng.uniform(0.4, 0.7), -h * 0.2, w * 1.3, h * rng.uniform(0.4, 0.7)), fill=150
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(w // 20))
    return ImageChops.multiply(ImageChops.multiply(img, light), shadow)


def keystone(img, amount=0.08):
    """The page as a trapezoid, narrower at the top, on a dark table: a
    phone held tilted toward the page. QUAD maps the output rectangle onto
    a source quad that is wider at the top than the page."""
    w, h = img.size
    pad, d = int(w * 0.12), w * amount
    table = Image.new("L", (w + 2 * pad, h + 2 * pad), 90)
    table.paste(img, (pad, pad))
    # Corners: upper-left, lower-left, lower-right, upper-right.
    quad = (pad - d - pad / 2, pad / 2, pad / 2, h + 1.5 * pad,
            w + 1.5 * pad, h + 1.5 * pad, w + pad + d + pad / 2, pad / 2)
    return table.transform(table.size, Image.QUAD, quad, resample=Image.BICUBIC, fillcolor=90)


def jpeg(img, quality):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def samples(rng):
    t = iter(TEXTS)

    img, gt = render(next(t), "arial", 42)
    yield "scan_arial", img, gt

    img, gt = render(next(t), "times", 40)
    yield "scan_times", img, gt

    img, gt = render(next(t), "arial", 42)
    yield "messenger_small", jpeg(img.resize((900, img.height * 900 // img.width), Image.LANCZOS), 60), gt

    img, gt = render(next(t), "arial", 44)
    img = uneven_light(img, rng).rotate(3, resample=Image.BICUBIC, expand=True, fillcolor=120)
    yield "photo_shadow_tilt", jpeg(img.filter(ImageFilter.GaussianBlur(1.2)), 75), gt

    img, gt = render(next(t), "times", 44)
    img = uneven_light(img, rng)
    img = keystone(img)
    yield "photo_keystone", jpeg(img.resize((1600, 1600 * img.height // img.width), Image.LANCZOS), 80), gt

    img, gt = render(next(t), "arial", 17, width=1200, fg=225, bg=32, margin=40)
    yield "dark_screenshot", img, gt

    img, gt = render(next(t), "arial", 96)
    yield "large_print", img, gt

    img, gt = render(next(t), "courier", 40)
    img = uneven_light(img, rng).filter(ImageFilter.GaussianBlur(0.8))
    yield "typewriter_photo", jpeg(img, 70), gt


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(7)
    for name, img, gt in samples(rng):
        img.save(os.path.join(out_dir, name + ".png"))
        with open(os.path.join(out_dir, name + ".gt.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(gt) + "\n")
        print(name, img.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tests/bench/synthetic")
