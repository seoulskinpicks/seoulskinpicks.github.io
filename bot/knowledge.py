"""Built-in knowledge used by the template copywriter.

Everything here is category-level, general-use information (how a toner is
typically used, what a gua sha is). It never makes claims about a specific
product, so template posts stay honest even without AI.
"""
from __future__ import annotations

import re

ROUTINE_STEPS = [
    ("Cleanse", "oil + gentle cleanser"),
    ("Prep", "toner / essence"),
    ("Treat", "serum / mask"),
    ("Moisturize", "cream / gel"),
    ("Protect", "sunscreen, mornings"),
]

# ---------------------------------------------------------------------------
# K-beauty product categories (for rows in the Google Sheet)
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, dict] = {
    "cleansing_oil": {
        "label": "cleansing oil",
        "aliases": ["cleansing oil", "cleansing balm", "oil cleanser", "balm", "클렌징오일", "클렌징 오일", "클렌징밤", "클렌징 밤"],
        "what": [
            "Step one of the Korean double cleanse",
            "Melts sunscreen and makeup so your cleanser can finish the job",
            "Turns milky and rinses off when it meets water",
        ],
        "how": [
            "Apply to a dry face with dry hands",
            "Massage for about a minute to melt makeup and sunscreen",
            "Add a splash of water, rinse, then follow with a gentle cleanser",
        ],
        "routine": 0,
        "note": "Evenings, before your water-based cleanser.",
        "tags": ["#doublecleanse", "#cleansingoil"],
    },
    "cleanser": {
        "label": "cleanser",
        "aliases": ["cleanser", "cleansing foam", "foam", "face wash", "gel cleanser", "클렌저", "폼클렌징", "폼 클렌징", "클렌징폼", "세안제"],
        "what": [
            "The second step of the Korean double cleanse",
            "Washes away sweat, oil and leftover residue",
            "Gentle formulas are the norm in Korean routines",
        ],
        "how": [
            "Wet your face and work a small amount into a lather",
            "Massage gently for 30 to 60 seconds",
            "Rinse with lukewarm water and pat dry",
        ],
        "routine": 0,
        "note": "Morning and night, as your cleansing step.",
        "tags": ["#doublecleanse", "#koreancleanser"],
    },
    "toner_pad": {
        "label": "toner pad",
        "aliases": ["toner pad", "toner pads", "pad", "pads", "토너패드", "토너 패드", "패드"],
        "what": [
            "Pre-soaked pads that make toning a one-swipe step",
            "Many are made for gentle exfoliation or quick hydration",
            "A go-to for busy mornings in Korea",
        ],
        "how": [
            "After cleansing, swipe one pad across your face",
            "Flip it over and pat in the leftover liquid",
            "If it's an exfoliating pad, start with a few times a week",
        ],
        "routine": 1,
        "note": "Right after cleansing, before serum.",
        "tags": ["#tonerpads", "#koreantoner"],
    },
    "toner": {
        "label": "toner",
        "aliases": ["toner", "skin", "토너", "스킨"],
        "what": [
            "The first leave-on step after cleansing",
            "Adds a light first layer of hydration",
            "Preps skin for the steps that come next",
        ],
        "how": [
            "After cleansing, pour a little into your palms or onto a cotton pad",
            "Pat it gently into your face and neck",
            "Follow with serum and moisturizer",
        ],
        "routine": 1,
        "note": "Right after cleansing, before serum.",
        "tags": ["#koreantoner", "#hydratingtoner"],
    },
    "essence": {
        "label": "essence",
        "aliases": ["essence", "에센스"],
        "what": [
            "A watery layer between toner and serum",
            "A classic step in Korean routines",
            "Adds hydration without feeling heavy",
        ],
        "how": [
            "After toner, pour a few drops into your palms",
            "Press gently into your skin until absorbed",
            "Follow with serum and moisturizer",
        ],
        "routine": 1,
        "note": "After toner, before serum.",
        "tags": ["#koreanessence"],
    },
    "serum": {
        "label": "serum",
        "aliases": ["serum", "ampoule", "ampule", "booster", "세럼", "앰플", "앰풀", "부스터"],
        "what": [
            "A concentrated step for your main skin goal",
            "Goes on after toner, before cream",
            "Ampoules are the extra-concentrated Korean version",
        ],
        "how": [
            "Apply 2 to 3 drops after toner",
            "Pat it in gently instead of rubbing",
            "Seal it in with a moisturizer",
        ],
        "routine": 2,
        "note": "After toner, before moisturizer.",
        "tags": ["#koreanserum", "#ampoule"],
    },
    "sheet_mask": {
        "label": "sheet mask",
        "aliases": ["sheet mask", "mask pack", "mask sheet", "마스크팩", "시트마스크", "시트 마스크", "마스크 팩"],
        "what": [
            "A serum-soaked sheet for a quick hydration boost",
            "Korea's favorite night-in self-care step",
            "An easy way to add a treat to your routine",
        ],
        "how": [
            "After toner, smooth the sheet over your face",
            "Relax for the time on the pack, usually 15 to 20 minutes",
            "Remove it and pat the leftover essence in",
        ],
        "routine": 2,
        "note": "After toner, a few evenings a week.",
        "tags": ["#sheetmask", "#maskpack"],
    },
    "wash_off_mask": {
        "label": "wash-off mask",
        "aliases": ["wash off mask", "wash-off mask", "clay mask", "mud mask", "워시오프", "워시 오프", "머드팩", "클레이"],
        "what": [
            "A rinse-off treatment you use once or twice a week",
            "Clay types are popular for oily T-zones",
            "A simple weekend reset for your skin",
        ],
        "how": [
            "Apply a thin, even layer to clean, dry skin",
            "Leave it on for the time on the pack and don't let it crack",
            "Rinse with lukewarm water and follow with toner",
        ],
        "routine": 2,
        "note": "After cleansing, once or twice a week.",
        "tags": ["#claymask", "#washoffmask"],
    },
    "eye_cream": {
        "label": "eye cream",
        "aliases": ["eye cream", "eye serum", "아이크림", "아이 크림"],
        "what": [
            "A lighter-touch formula for the delicate eye area",
            "Goes on before your regular moisturizer",
            "A small step many Korean routines include",
        ],
        "how": [
            "Take a rice-grain-sized amount on your ring finger",
            "Tap gently around the orbital bone, never tug",
            "Let it settle before moisturizer",
        ],
        "routine": 2,
        "note": "After serum, before moisturizer.",
        "tags": ["#eyecream"],
    },
    "spot_care": {
        "label": "spot care",
        "aliases": ["pimple patch", "spot patch", "spot care", "spot treatment", "acne patch", "여드름패치", "여드름 패치", "스팟", "트러블"],
        "what": [
            "Tiny patches or gels for a single spot",
            "Patches keep your hands off while you wait it out",
            "A pouch essential in Korea",
        ],
        "how": [
            "Cleanse the area and let it dry completely",
            "Apply the patch or a small dot of treatment",
            "Leave it on overnight or as the pack directs",
        ],
        "routine": 2,
        "note": "On clean, dry skin, as needed.",
        "tags": ["#pimplepatch", "#spotcare"],
    },
    "moisturizer": {
        "label": "moisturizer",
        "aliases": ["moisturizer", "moisturiser", "cream", "gel cream", "lotion", "emulsion", "크림", "수분크림", "수분 크림", "로션", "에멀전"],
        "what": [
            "The step that locks in everything underneath",
            "Korean creams come in textures from airy gel to rich cream",
            "Keeps skin comfortable through the day or night",
        ],
        "how": [
            "Warm a small amount between your fingertips",
            "Press it over your face and neck",
            "In the morning, follow with sunscreen",
        ],
        "routine": 3,
        "note": "After serum, before sunscreen.",
        "tags": ["#moisturizer", "#koreancream"],
    },
    "sunscreen": {
        "label": "sunscreen",
        "aliases": ["sunscreen", "sun cream", "sunblock", "sun stick", "sun serum", "spf", "선크림", "선 크림", "선스틱", "선 스틱", "선세럼", "선블록"],
        "what": [
            "The step Korean routines never skip",
            "Korean sunscreens are known for light, wearable textures",
            "Your daily shield against UV exposure",
        ],
        "how": [
            "Use it as the last step of your morning routine",
            "Apply generously, about two finger-lengths for face and neck",
            "Reapply every 2 hours when you're outdoors",
        ],
        "routine": 4,
        "note": "Last step, every morning.",
        "tags": ["#koreansunscreen", "#spfeveryday"],
    },
    "lip": {
        "label": "lip tint",
        "aliases": ["lip", "lip tint", "tint", "lip balm", "lip gloss", "lipstick", "립", "립틴트", "립 틴트", "틴트", "립밤", "립글로스"],
        "what": [
            "Korean tints are loved for a soft, natural flush",
            "Stain-style formulas tend to stay put",
            "Easy to build from sheer to bold",
        ],
        "how": [
            "Start with a dot in the center of your lips",
            "Blot with a fingertip for a soft gradient",
            "Layer again for more color",
        ],
        "routine": None,
        "tips": [
            "Apply to the inner lip only for the classic gradient look",
            "Add a balm on top for extra shine",
            "Tap a little on your cheeks for a matching flush",
        ],
        "tags": ["#liptint", "#kbeautymakeup"],
    },
    "cushion": {
        "label": "cushion",
        "aliases": ["cushion", "cushion foundation", "foundation", "쿠션", "파운데이션"],
        "what": [
            "The Korean compact behind the dewy-skin look",
            "Foundation held in a sponge for easy touch-ups",
            "Usually sheer-to-medium, skin-like coverage",
        ],
        "how": [
            "Press the puff lightly into the cushion",
            "Tap from the center of your face outward instead of dragging",
            "Add a second thin layer only where you need it",
        ],
        "routine": None,
        "tips": [
            "Wash or swap the puff often",
            "Set only your T-zone to keep the glow",
            "Close it tightly so it doesn't dry out",
        ],
        "tags": ["#cushionfoundation", "#kbeautymakeup"],
    },
    "hair": {
        "label": "hair care",
        "aliases": ["hair", "shampoo", "hair treatment", "hair oil", "hair mask", "scalp", "헤어", "샴푸", "트리트먼트", "헤어오일", "헤어 오일", "두피"],
        "what": [
            "Korean routines treat the scalp like skin",
            "Hair care is a big category at Olive Young",
            "Small swaps here can change how your hair feels",
        ],
        "how": [
            "Focus shampoo on the scalp and treatment on the lengths",
            "Leave treatments on for the time on the pack",
            "Rinse with lukewarm, not hot, water",
        ],
        "routine": None,
        "tips": [
            "Massage your scalp for a minute while you shampoo",
            "Use hair oil on damp ends only",
            "Let hair dry partly before heat styling",
        ],
        "tags": ["#koreanhaircare", "#scalpcare"],
    },
    "other": {
        "label": "pick",
        "aliases": [],
        "what": [
            "A current favorite in Korean beauty stores",
            "Picked from what shoppers in Korea are buying now",
            "Here's how to fit it into your routine",
        ],
        "how": [
            "Check the label for when to use it: AM, PM or both",
            "Patch-test on a small area first",
            "Add it to your routine one product at a time",
        ],
        "routine": None,
        "tips": [
            "Patch-test anything new",
            "Introduce one new product at a time",
            "Give it a few weeks before you judge",
        ],
        "tags": [],
    },
}


def match_category(text: str) -> str:
    """Map whatever the user typed ("선크림", "Sun Stick", "toner pads") to a key."""
    t = (text or "").strip().lower()
    if not t:
        return "other"
    if t in CATEGORIES:
        return t
    if re.search(r"\bpads?\b", t) and re.search(r"toner|peel|exfoliat|cotton", t):
        return "toner_pad"
    best, best_len = "other", 0
    for key, cat in CATEGORIES.items():
        for alias in cat["aliases"]:
            a = alias.lower()
            if a == t:
                return key
            if a in t and len(a) > best_len:
                best, best_len = key, len(a)
    return best


# ---------------------------------------------------------------------------
# Beauty tools searched on AliExpress (non-electric, not applied to skin)
# `must`: every group needs at least one match in the product title.
# ---------------------------------------------------------------------------
TOOLS: dict[str, dict] = {
    "gua_sha": {
        "query": "gua sha facial tool",
        "must": [["gua sha", "guasha"]],
        "name": "Gua sha stone",
        "what": [
            "A smooth stone you glide over your face with oil",
            "A facial-massage tool with centuries of history",
            "Many people love it as a slow morning ritual",
        ],
        "how": [
            "Apply a face oil or serum first, never on dry skin",
            "Hold it almost flat and sweep up and out, 3 to 5 strokes per area",
            "Keep the pressure light and skip irritated or broken skin",
        ],
        "hooks": ["The under-${price} stone for a slow morning ritual", "Gua sha for under ${price}? Here's how to use it"],
        "tags": ["#guasha", "#facialmassage"],
    },
    "ice_roller": {
        "query": "ice roller face",
        "must": [["ice roller", "ice face roller", "cold roller"]],
        "name": "Ice roller",
        "what": [
            "A roller that lives in your freezer",
            "Cold rolling is a popular wake-up trick",
            "Feels amazing after a long day or a hot shower",
        ],
        "how": [
            "Store it in the freezer, or the fridge for a milder chill",
            "Roll outward from the center of your face for 1 to 2 minutes",
            "Keep it moving, and wrap it in a tissue if it feels too cold",
        ],
        "hooks": ["The under-${price} freezer trick for sleepy mornings", "Why so many freezers have an ice roller in them"],
        "tags": ["#iceroller", "#morningroutine"],
    },
    "face_roller": {
        "query": "jade face roller",
        "must": [["face roller", "facial roller", "jade roller", "quartz roller", "massage roller"]],
        "exclude": ["ice"],
        "name": "Facial roller",
        "what": [
            "A cool stone roller for a relaxing face massage",
            "Pairs well with your serum or face oil",
            "A calm, screen-free minute in your routine",
        ],
        "how": [
            "Apply serum or oil so the roller glides",
            "Roll up and outward from the center of your face",
            "Wipe it clean after each use",
        ],
        "hooks": ["The under-${price} tool for a 2-minute face massage", "A facial roller, explained in 5 slides"],
        "tags": ["#jaderoller", "#facemassage"],
    },
    "silicone_scrubber": {
        "query": "silicone face cleansing brush manual",
        "must": [["silicone"], ["cleansing brush", "face brush", "facial brush", "face scrubber", "cleansing pad", "face wash brush", "facial cleansing"]],
        "name": "Silicone cleansing pad",
        "what": [
            "Soft silicone bristles for your cleanser",
            "Rinses clean and dries fast, unlike cloth",
            "Makes the double cleanse feel extra thorough",
        ],
        "how": [
            "Wet your face and the pad, then add your cleanser",
            "Massage in small, gentle circles for 30 to 60 seconds",
            "Rinse the pad and let it air-dry",
        ],
        "hooks": ["The under-${price} upgrade for your double cleanse", "Your cleanser's new best friend (under ${price})"],
        "tags": ["#doublecleanse", "#cleansingbrush"],
    },
    "mask_brush": {
        "query": "silicone face mask brush",
        "must": [["mask brush", "mask applicator", "mask spatula"]],
        "name": "Mask applicator brush",
        "what": [
            "Spreads clay and wash-off masks evenly",
            "Keeps your fingers clean and wastes less product",
            "A small tool that makes mask night feel like a spa",
        ],
        "how": [
            "Scoop a little mask onto the brush",
            "Paint a thin, even layer from the center outward",
            "Rinse the brush with soap and let it dry",
        ],
        "hooks": ["The under-${price} tool that upgrades mask night", "Mask night, but make it a spa (under ${price})"],
        "tags": ["#masknight", "#selfcaresunday"],
    },
    "makeup_sponge": {
        "query": "makeup blender sponge",
        "must": [["makeup sponge", "blender sponge", "beauty sponge", "makeup blender", "sponge puff"]],
        "name": "Makeup sponge",
        "what": [
            "Presses base into skin for a natural finish",
            "The tool behind the soft, skin-like K-beauty base",
            "Works with cushion, foundation and concealer",
        ],
        "how": [
            "Dampen it and squeeze out the extra water",
            "Bounce, don't swipe, from the center of your face outward",
            "Wash it weekly and replace it every few months",
        ],
        "hooks": ["The under-${price} secret to a skin-like base", "How Koreans get that soft-focus base"],
        "tags": ["#makeupsponge", "#kbeautymakeup"],
    },
    "brush_set": {
        "query": "makeup brush set soft",
        "must": [["brush set", "brushes set", "makeup brushes", "cosmetic brushes"]],
        "name": "Makeup brush set",
        "what": [
            "Soft brushes for base, blush and eyes",
            "A full set for less than one department-store brush",
            "Great for a travel kit or your first brush collection",
        ],
        "how": [
            "Use dense brushes for base and fluffy ones for powder",
            "Tap off extra product before you apply",
            "Wash weekly with gentle soap and dry them flat",
        ],
        "hooks": ["A full brush set for under ${price}", "The under-${price} brush set for soft K-beauty makeup"],
        "tags": ["#makeupbrushes", "#kbeautymakeup"],
    },
    "spa_headband": {
        "query": "spa headband skincare",
        "must": [["headband", "hair band", "hairband"], ["spa", "skincare", "skin care", "makeup", "face wash", "washing", "facial"]],
        "name": "Skincare headband",
        "what": [
            "Keeps hair out of the way while you cleanse",
            "Makes a 10-step routine feel like a spa",
            "Soft fabric that's gentle on your hairline",
        ],
        "how": [
            "Slip it on before you start cleansing",
            "Push it back from your hairline so no product gets caught",
            "Toss it in the wash every week",
        ],
        "hooks": ["The under-${price} thing that makes skincare feel like a spa", "Your routine, but cozier (under ${price})"],
        "tags": ["#spaheadband", "#selfcare"],
    },
    "konjac_sponge": {
        "query": "konjac sponge face",
        "must": [["konjac"]],
        "name": "Konjac sponge",
        "what": [
            "A natural sponge made from konjac root",
            "A classic in Korean and Japanese routines",
            "Very soft when wet, great for gentle cleansing",
        ],
        "how": [
            "Soak it in warm water until it's soft",
            "Use it alone or with cleanser in gentle circles",
            "Squeeze it out and hang it to dry",
        ],
        "hooks": ["The under-${price} sponge made from a root vegetable", "Konjac sponge: the gentle cleansing classic"],
        "tags": ["#konjacsponge", "#gentlecleansing"],
    },
    "scalp_massager": {
        "query": "scalp massager shampoo brush",
        "must": [["scalp massager", "scalp brush", "shampoo brush", "scalp scrubber", "scalp care brush", "head massager"]],
        "name": "Scalp massage brush",
        "what": [
            "Korean routines treat the scalp like skin",
            "Helps work shampoo through thick hair",
            "Feels like a salon head massage at home",
        ],
        "how": [
            "Apply shampoo to wet hair first",
            "Move the brush in small circles across your scalp",
            "Rinse the brush and let it dry",
        ],
        "hooks": ["The under-${price} tool for Korean-style scalp care", "Scalp care is the new skincare (under ${price})"],
        "tags": ["#scalpcare", "#koreanhaircare"],
    },
    "eyelash_curler": {
        "query": "eyelash curler",
        "must": [["eyelash curler", "lash curler"]],
        "exclude": ["heated"],
        "name": "Eyelash curler",
        "what": [
            "The step before mascara for open-looking eyes",
            "A staple in Korean makeup pouches",
            "Small tool, very visible difference",
        ],
        "how": [
            "Curl before mascara, never after",
            "Clamp gently at the base for a few seconds",
            "Walk it up the lashes for a soft curve",
        ],
        "hooks": ["The under-${price} tool for wide-awake eyes", "Why this tiny tool is in every K-beauty pouch"],
        "tags": ["#eyelashcurler", "#kbeautymakeup"],
    },
    "reusable_pads": {
        "query": "reusable makeup remover pads",
        "must": [["reusable", "washable"], ["pad", "pads", "cotton round", "rounds"]],
        "name": "Reusable cotton rounds",
        "what": [
            "Washable rounds for toner and makeup removal",
            "Less waste than single-use cotton",
            "Soft enough for patting toner into skin",
        ],
        "how": [
            "Soak one with toner or micellar water",
            "Wipe or pat gently over your face",
            "Toss them in the laundry bag and reuse",
        ],
        "hooks": ["The under-${price} swap for single-use cotton pads", "Your toner step, now zero-waste"],
        "tags": ["#reusablepads", "#sustainablebeauty"],
    },
}

# Titles containing any of these are skipped: brand names (counterfeit risk),
# products you put on skin, electronics/medical devices and "copy" wording.
BLOCKED_PATTERNS = [
    # brands frequently counterfeited
    r"\bdyson\b", r"\bchanel\b", r"\bdior\b", r"\bgucci\b", r"\bmac\b", r"\bfenty\b", r"rare beauty",
    r"\bsephora\b", r"charlotte tilbury", r"\bnars\b", r"est[eé]e lauder", r"\blanc[oô]me\b", r"\bclinique\b",
    r"\bolaplex\b", r"\bglossier\b", r"\blaneige\b", r"\bcosrx\b", r"\bsulwhasoo\b", r"\bforeo\b", r"\bnuface\b",
    r"\brefa\b", r"mount lai", r"\btatcha\b", r"drunk elephant", r"the ordinary", r"\bcerave\b", r"la roche",
    r"real techniques", r"\bsigma\b", r"\bmorphe\b", r"beauty ?blender", r"tangle teezer", r"\bghd\b",
    r"\bshiseido\b", r"sk-?ii", r"\btarte\b", r"too faced", r"\bhuda\b", r"anastasia", r"urban decay",
    r"\bbenefit\b", r"bobbi brown", r"\barmani\b", r"\bysl\b", r"saint laurent", r"\bmedicube\b", r"\bkylie\b",
    # things applied to skin / ingestibles
    r"\bcreams?\b", r"\bserums?\b", r"\blotion\b", r"\bessence\b", r"\btoner\b(?! pad)", r"sunscreen", r"\bspf\b",
    r"sheet mask", r"mask sheet", r"mud mask", r"clay mask", r"\bpeel", r"whitening", r"bleach", r"lightening",
    r"\bacid\b", r"retinol", r"collagen", r"capsule", r"\bpills?\b", r"supplement", r"\bface oil\b", r"essential oil",
    # electronics & medical-style devices
    r"\bled\b", r"microcurrent", r"\bems\b", r"\brf\b", r"radio ?frequency", r"ultrasonic", r"\blaser\b", r"\bipl\b",
    r"derma ?roller", r"micro ?needl", r"\bneedles?\b", r"electric", r"\busb\b", r"rechargeable", r"battery", r"vibrat",
    # replica wording
    r"replica", r"\b1:1\b", r"original brand", r"\bcopy\b", r"\bdupe\b", r"inspired by", r"same as",
]


def blocked_reason(title: str, extra: list[str] | None = None) -> str | None:
    t = (title or "").lower()
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, t):
            return pat
    for word in extra or []:
        if word and word.lower() in t:
            return word
    return None


def matches_tool(title: str, tool_key: str) -> bool:
    tool = TOOLS[tool_key]
    t = (title or "").lower()
    if any(x in t for x in tool.get("exclude", [])):
        return False
    return all(any(w in t for w in group) for group in tool["must"])


MATERIALS = ["rose quartz", "jade", "amethyst", "obsidian", "bian stone", "stainless steel", "bamboo charcoal", "silicone", "ceramic"]


def detect_material(title: str) -> str | None:
    t = (title or "").lower()
    for m in MATERIALS:
        if m in t:
            return m
    return None
