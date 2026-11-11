"""Closed lexicons for the faithfulness verifier (data only, no logic).

Nothing here is shared with the diary generator: the generator authors are *told* about these
lists (see docs/prototypes/R2-faithfulness.md, "writer's contract") but must not import them to
build sentences. LEXICON_VERSION changes whenever a list changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

LEXICON_VERSION = 1


def _w(s: str) -> frozenset[str]:
    return frozenset(s.split())


def load_safe_vocabulary(path: Path | None = None) -> tuple[frozenset[str], str]:
    path = path or Path(__file__).with_name("lexicon_safe.txt")
    words: set[str] = set()
    version = "?"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("# version:"):
            version = line.split(":", 1)[1].strip()
        if not line or line.startswith("#"):
            continue
        words.update(line.lower().split())
    return frozenset(words), version


SAFE, SAFE_VERSION = load_safe_vocabulary()

# Grammar words that assert nothing. Deliberately absent: negation (not, no, never, n't forms),
# "again/still/already/finally/even/only", comparatives, he/she (people), you.
FUNCTION = _w(
    "a an the this that these those it its i me my mine myself am is are was were be been being "
    "have has had having do does did will would could can and or but so as if than when where "
    "while which what who to of in on at by for from with into onto over under up down out off "
    "through across along towards toward past between behind beside above below beyond inside "
    "outside within until till upon via per own all one they them their "
    "i'd i'm i've i'll it's that's there's they'd they're"
)
FIRST_PERSON_PLURAL = _w("we us our ours ourselves we'd we're we've we'll")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_ABBR = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5,
                "sun": 6}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
              "oct": 10, "nov": 11, "dec": 12}

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_MULT = {"hundred": 100, "thousand": 1000, "dozen": 12}

# unit → (dimension, factor to base unit). Base: km, metres, minutes.
UNITS = {
    "km": ("distance", 1.0), "kms": ("distance", 1.0), "kilometre": ("distance", 1.0),
    "kilometres": ("distance", 1.0), "kilometer": ("distance", 1.0), "kilometers": ("distance", 1.0),
    "mi": ("distance", 1.609344), "mile": ("distance", 1.609344), "miles": ("distance", 1.609344),
    "m": ("metres", 1.0), "metre": ("metres", 1.0), "metres": ("metres", 1.0), "meter": ("metres", 1.0),
    "meters": ("metres", 1.0), "ft": ("metres", 0.3048), "foot": ("metres", 0.3048),
    "feet": ("metres", 0.3048),
    "h": ("duration", 60.0), "hr": ("duration", 60.0), "hrs": ("duration", 60.0), "hour": ("duration", 60.0),
    "hours": ("duration", 60.0), "min": ("duration", 1.0), "mins": ("duration", 1.0),
    "minute": ("duration", 1.0), "minutes": ("duration", 1.0),
}
PHOTO_NOUNS = _w("photo photos picture pictures shot shots photograph photographs pics pic frames")

# name-part words that do not identify a place on their own (safe to drop / never enough alone)
NAME_CONNECTORS = _w("de du da do dos das des del della di la le les el al van von der den of the am an im "
                     "sur sous en y e a aux d l")
NAME_GENERIC = _w(
    "miradouro mirador viewpoint refuge refugio rifugio hut cabane lac lake lago col pass mount mont monte "
    "gara gare station bahnhof hauptbahnhof hbf market mercado museum museu musee church igreja cathedral "
    "hotel hostel cafe pastelaria taberna restaurant restaurante castle castelo bridge ponte square praca "
    "plaza street rua avenida park parque old town north south east west nord sud est ouest saint st "
    "santa san sao new upper lower central city"
)

# ---------------------------------------------------------------------------------------------
# hedges
# ---------------------------------------------------------------------------------------------
HEDGE_LOCAL = [  # hedge the claim that starts within 3 tokens after the phrase
    "around", "about", "roughly", "approximately", "approx", "nearly", "almost", "some", "circa",
    "close to", "something like", "more or less", "near", "somewhere near", "somewhere around",
    "somewhere", "just under", "just over", "a little over", "a little under", "a bit over",
    "a bit under", "what looked like", "what must have been",
]
HEDGE_SENTENCE = [  # hedge every claim in the sentence
    "i think", "we think", "i guess", "i believe", "i reckon", "probably", "must have", "seems",
    "seemed", "seem", "apparently", "presumably", "maybe", "perhaps", "possibly", "likely",
    "as far as i can tell", "if the track is right", "judging by the photos",
]
HEDGE_POST = ["or so", "or thereabouts", "give or take", "more or less"]
DIRECTION_UP = ["over", "more than", "at least", "just over", "a little over", "a bit over"]
DIRECTION_DOWN = ["under", "less than", "at most", "nearly", "almost", "just under", "a little under",
                  "a bit under"]

SEQUENCE_WORDS = _w("then later afterwards afterward after before next earlier")

# ---------------------------------------------------------------------------------------------
# parts of day: name → (window start, end) in minutes of local day; None = only by tag/payload
# ---------------------------------------------------------------------------------------------
PARTS_OF_DAY: dict[str, tuple[str, tuple[int, int] | None]] = {
    "morning": ("morning", (300, 720)), "mornings": ("morning", (300, 720)),
    "afternoon": ("afternoon", (720, 1080)),
    "evening": ("evening", (1020, 1380)), "tonight": ("evening", (1020, 1500)),
    "night": ("night", (1260, 1740)), "overnight": ("night", (1260, 1740)),
    "noon": ("noon", (690, 780)), "midday": ("noon", (690, 780)), "lunchtime": ("noon", (690, 870)),
    "sunrise": ("sunrise", None), "dawn": ("sunrise", None), "daybreak": ("sunrise", None),
    "sunset": ("sunset", None), "dusk": ("sunset", None), "twilight": ("sunset", None),
    "early": ("early", (240, 510)), "late": ("late", (1260, 1740)),
}
PART_ALIASES = {"sunrise": {"sunrise", "dawn"}, "sunset": {"sunset", "dusk"}, "noon": {"noon", "midday"},
                "night": {"night"}, "evening": {"evening"}, "morning": {"morning"},
                "afternoon": {"afternoon"}}


# ---------------------------------------------------------------------------------------------
# activities: word → what evidence supports it
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Act:
    key: str
    claim_kind: str = "activity"                 # "activity" | "transport"
    kinds: frozenset[str] = frozenset()          # `kind` evidence
    modes: frozenset[str] = frozenset()          # `transport` / `movement` mode
    categories: frozenset[str] = frozenset()     # `place` category
    tags: frozenset[str] = frozenset()           # `visual` tags
    types: frozenset[str] = frozenset()          # mere presence of an evidence type
    window: tuple[int, int] | None = None        # required local start time window (meals)
    forms: frozenset[str] = field(default_factory=frozenset)


def _act(key, forms, claim_kind="activity", kinds="", modes="", categories="", tags="", types="", window=None):
    return Act(key, claim_kind, _w(kinds), _w(modes), _w(categories), _w(tags), _w(types), window, _w(forms))


_ACTS = [
    _act("walk", "walk walked walking walks stroll strolled strolling wander wandered wandering foot",
         kinds="walk", modes="walk"),
    _act("hike", "hike hiked hiking hikes trek trekked trekking trail", kinds="hike summit", modes="hike"),
    _act("climb", "climb climbed climbing climbs ascent descent descended descend ascended",
         kinds="hike summit", modes="hike", types="elevation"),
    _act("swim", "swim swam swimming swum dip dipped", kinds="swim"),
    _act("train", "train trains rail rails railway carriage", "transport", modes="train"),
    _act("station", "station platform", kinds="station", categories="station train_station railway_station",
         modes="train"),
    _act("tram", "tram trams streetcar", "transport", modes="tram"),
    _act("bus", "bus buses coach", "transport", modes="bus"),
    _act("boat", "boat boats ferry ferries sailed sailing sail cruise", "transport", modes="boat"),
    _act("car", "car drove drive driving driven taxi cab", "transport", modes="car"),
    _act("bike", "bike biked cycling cycled cycle bicycle", "transport", modes="bike"),
    _act("flight", "flight flew fly flying plane airport landed", "transport", modes="flight"),
    _act("transit", "boarded board rode", "transport", types="transport", kinds="transit"),
    _act("museum", "museum museums gallery exhibition exhibit", kinds="museum", categories="museum gallery"),
    _act("market", "market markets stall stalls", kinds="market", categories="market marketplace food_court"),
    _act("meal", "ate eat eating eaten meal restaurant", kinds="meal", categories="restaurant"),
    _act("breakfast", "breakfast", kinds="meal cafe", window=(300, 660)),
    _act("lunch", "lunch lunched", kinds="meal", window=(660, 930)),
    _act("dinner", "dinner dined supper", kinds="meal", window=(1050, 1439)),
    _act("coffee", "coffee coffees cafe", kinds="cafe", categories="cafe coffee_shop"),
    _act("bar", "bar pub beer beers wine drink drinks drank pint", kinds="bar", categories="bar pub"),
    _act("viewpoint", "viewpoint lookout view views overlook panorama", kinds="viewpoint",
         categories="viewpoint"),
    _act("sight", "sight sights sightseeing monument", kinds="sight"),
    _act("lodging", "hotel hostel hut refuge slept sleep bed room camp camped tent bunk", kinds="lodging",
         categories="hotel hostel hut alpine_hut guesthouse campsite"),
    _act("summit", "summit summited peak top", kinds="summit", categories="peak summit"),
    _act("pass", "pass col saddle", categories="pass saddle col"),
    _act("lake", "lake lakes tarn", categories="lake", tags="lake"),
    _act("beach", "beach sand shore", kinds="beach", categories="beach", tags="beach sand"),
    _act("worship", "church cathedral mosque temple chapel monastery", kinds="worship",
         categories="church cathedral mosque temple"),
    _act("shop", "shop shops shopping bought buy souvenir souvenirs", kinds="shop"),
    _act("park", "park garden gardens", kinds="park", categories="park garden"),
    _act("wildlife", "wildlife", kinds="wildlife"),
    _act("event", "concert festival", kinds="event"),
    _act("border", "border frontier", types="border"),
    _act("timezone", "timezone clocks clock", types="timezone_change"),
    _act("photo", "photo photos picture pictures shot shots photographed photograph photographs camera",
         types="photo_count visual"),
    _act("city", "city town village", types="locality"),
    _act("country", "country countries", types="locality border first"),
]
ACTIVITY: dict[str, Act] = {form: a for a in _ACTS for form in a.forms}
# "pass" the noun collides with the safe verb; the noun wins only as an exact form (see verify.py).

FOOD = _w(
    "sardine sardines grilled pastel nata pasteis goulash soup bread cheese fondue pizza pasta sandwich "
    "salad steak fish cod bacalhau octopus prawns shrimp oysters mussels rice noodles ramen sushi curry "
    "dumplings pierogi schnitzel strudel cake pastry pastries croissant tart custard chocolate gelato "
    "sausage sausages ham eggs omelette toast burger fries chips kebab stew langos tea juice lemonade "
    "cocktail spritz espresso cappuccino latte tapas paella risotto potatoes chicken pork beef lamb duck "
    "tuna salmon olives honey jam butter yoghurt porridge apple cherries figs grapes nuts snack snacks "
    "picnic dessert raclette crepe crepes waffle pancake pancakes pretzel fried roasted baked smoked "
    "spicy seafood"
)
WEATHER = _w(
    "sun sunny sunshine rain rained raining rainy drizzle shower showers wind windy breeze breezy fog foggy "
    "mist misty cloud clouds cloudy overcast storm stormy thunder lightning hail snowing snowed hot warm "
    "mild cold chilly cool freezing frost frosty icy heat humid muggy dry wet weather forecast temperature "
    "degrees drenched soaked sunburn sunburnt"
)
# weather-like words a visual tag may support (word → tag)
WEATHER_BY_TAG = {"snow": "snow", "snowy": "snow", "snowfield": "snow"}
PEOPLE = _w(
    "friend friends brother sister mother mum mom father dad parents wife husband partner girlfriend "
    "boyfriend son daughter kids children family cousin uncle aunt colleague mate waiter waitress barman "
    "bartender barista guide driver conductor owner host hostess guard ranger hiker hikers climber climbers "
    "tourist tourists locals local stranger strangers couple people person man woman guy girl boy lady "
    "someone somebody everyone everybody nobody anyone crowd crowds crowded group together alone met meet "
    "chatted chat talked talk joined he she his her him you your company companion neighbour neighbours"
)
FEELING = _w(
    "delicious tasty amazing wonderful beautiful lovely gorgeous stunning breathtaking spectacular incredible "
    "fantastic great good nice fine pleasant perfect magical glorious superb excellent brilliant awesome "
    "memorable unforgettable charming pretty cute cosy cozy quiet peaceful calm busy lively noisy hectic "
    "boring dull awful terrible horrible bad disappointing disappointed tired exhausted exhausting knackered "
    "shattered sore aching hungry starving thirsty happy glad pleased delighted thrilled excited relieved "
    "proud sad nervous scared afraid worried anxious bored annoyed frustrated grateful lucky loved love "
    "enjoyed enjoy liked like hated fun funny worth highlight treat reward rewarding tough hard easy brutal "
    "gruelling honestly sadly luckily happily unfortunately fortunately surprisingly wow felt feeling feel "
    "mood welcome friendly special magic bliss paradise dream joy pleasure shame pity relief surprise "
    "surprised impressive impressed interesting strange weird odd"
)
SUPERLATIVE = _w("best worst most least favourite favorite ever")
NOT_SUPERLATIVE = _w(
    "forest honest modest request interest harvest protest suggest contest arrest invest digest earnest "
    "tempest conquest west rest test nest guest chest quest crest priest manifest southwest northwest "
    "budapest bucharest"
)
