"""Hostile sets built with the ordinary engine: tiny3, vintage, stress5000."""

from __future__ import annotations

from ..spec import CameraSpec, TripBuilder
from ..util import rng_of

IPHONE = dict(make="Apple", model="iPhone 14", lens="iPhone 14 back dual wide camera 5.7mm f/1.5", prefix="IMG_",
              software="17.4.1", has_gps=True, writes_offset=True, tz_mode="auto", quality=88)


def tiny3(seed: int = 3):
    cams = [CameraSpec(id="phone", folder="iphone-14", start_no=212, notes="well-behaved phone", **IPHONE)]
    b = TripBuilder("tiny3", "Three photos in Lisbon", seed,
                    {"lat": 52.3702, "lon": 4.8952, "tz": "Europe/Amsterdam", "tz_offset_min": 120, "locality": "Amsterdam", "country_code": "NL"},
                    {"name": "Noor", "voice": "one-line captions, lower case, no fuss"}, cams,
                    "stopped for a coffee. good one. walked up the hill after, legs complaining. worth it for the view.",
                    sun=(6.3, 20.7), heic=0, exact_dups=0, near_dups=0, noexif=0, corrupt=(), no_offset_share=0.0,
                    p_nogps_out=0.0, p_nogps_in=0.0, portrait=0.0, has_track=False,
                    notes=["Exactly three photos, two moments 25 minutes and ~80 m apart."])
    b.day("2024-05-18", tz=60)
    b.m("11:55", 6, "lis/miradouro-de-santa-luzia", "viewpoint", "city_view", n=2, imp=4, look={"landmark": "dome"})
    b.m("12:26", 5, "lis/miradouro-das-portas-do-sol", "viewpoint", "waterfront", n=1, imp=3, look={"rail": True},
        hard="second viewpoint ~80 m from the first, 25 minutes later; one photo only")
    b.forbid("Visited the castle.", ["castelo", "castle"])
    return b
