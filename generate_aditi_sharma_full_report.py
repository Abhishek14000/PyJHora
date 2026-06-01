#!/usr/bin/env python3
import inspect
import json
from pathlib import Path
from typing import Any

from jhora import const, utils
from jhora.horoscope.chart import arudhas, ashtakavarga, charts, dosha, strength, yoga
from jhora.horoscope.main import Horoscope
from jhora.horoscope.prediction import general, longevity
from jhora.panchanga import drik


NAME = "Aditi Sharma"
DOB = drik.Date(2000, 11, 10)
TOB_STR = "22:10"
TOB_TUPLE = (22, 10, 0)
PLACE_NAME = "Noida, Uttar Pradesh, India"
JSON_OUT = Path("aditi_sharma_full_report.json")
MD_OUT = Path("aditi_sharma_full_report.md")


def _to_serializable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(v) for v in value]
    if hasattr(value, "_asdict"):
        return _to_serializable(value._asdict())
    if hasattr(value, "__dict__"):
        return _to_serializable(vars(value))
    return str(value)


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _markdown_for_value(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}- **{k}**:")
                lines.extend(_markdown_for_value(v, indent + 1))
            else:
                lines.append(f"{pad}- **{k}**: {_format_scalar(v)}")
        return lines
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_markdown_for_value(item, indent + 1))
            else:
                lines.append(f"{pad}- {_format_scalar(item)}")
        return lines
    return [f"{pad}- {_format_scalar(value)}"]


def _invoke_available_dhasa_methods(horo: Horoscope, dob_tuple, tob_tuple, place) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for method_name, method in inspect.getmembers(horo, predicate=callable):
        if not (method_name.startswith("_get_") and "dhasa" in method_name):
            continue
        signature = inspect.signature(method)
        kwargs = {}
        unsupported_required = []
        for p in signature.parameters.values():
            if p.name == "self":
                continue
            if p.name == "dob":
                kwargs["dob"] = dob_tuple
            elif p.name == "tob":
                kwargs["tob"] = tob_tuple
            elif p.name == "place":
                kwargs["place"] = place
            elif p.name == "jd":
                kwargs["jd"] = horo.julian_day
            elif p.name == "years":
                kwargs["years"] = 120
            elif p.default is inspect._empty:
                unsupported_required.append(p.name)
        if unsupported_required:
            results[method_name] = {"skipped": f"unsupported required args: {unsupported_required}"}
            continue
        try:
            results[method_name] = method(**kwargs)
        except Exception as exc:
            results[method_name] = {"error": str(exc)}
    return results


def build_report() -> dict[str, Any]:
    place = utils.get_place(PLACE_NAME)
    if place is None:
        raise RuntimeError(f"Built-in location lookup failed for: {PLACE_NAME}")

    horo = Horoscope(place_with_country_code=PLACE_NAME, date_in=DOB, birth_time=TOB_STR)
    jd = horo.julian_day
    dob_tuple = (DOB.year, DOB.month, DOB.day)

    calendar_info = horo.get_calendar_information()
    horoscope_info, horoscope_charts, horoscope_asc_houses = horo.get_horoscope_information()
    bhava_chart, bhava_chart_info, bhava_asc_house = horo.get_bhava_chart_information(jd, place, divisional_chart_factor=1)

    divisional_factors = sorted(set(const.division_chart_factors))
    divisional_charts = {}
    special_lagnas_by_chart = {}
    sphutas_by_chart = {}
    ava_saha_by_chart = {}
    for factor in divisional_factors:
        key = f"D{factor}"
        pp = charts.divisional_chart(jd, place, divisional_chart_factor=factor)
        divisional_charts[key] = {
            "planet_positions": pp,
            "house_chart": utils.get_house_planet_list_from_planet_positions(pp),
        }
        try:
            special_lagnas_by_chart[key] = horo.get_special_lagnas_for_chart(jd, place, divisional_chart_factor=factor)
        except Exception as exc:
            special_lagnas_by_chart[key] = {"error": str(exc)}
        try:
            sphutas_by_chart[key] = horo.get_sphutas_for_chart(jd, place, divisional_chart_factor=factor)
        except Exception as exc:
            sphutas_by_chart[key] = {"error": str(exc)}
        try:
            ava_saha_by_chart[key] = horo.get_ava_saha_yoga_info_for_chart(jd, place, divisional_chart_factor=factor)
        except Exception as exc:
            ava_saha_by_chart[key] = {"error": str(exc)}

    d1_positions = divisional_charts["D1"]["planet_positions"]
    d1_chart_1d = divisional_charts["D1"]["house_chart"]
    ashtaka_bav, ashtaka_sav, ashtaka_prastara = ashtakavarga.get_ashtaka_varga(d1_chart_1d)
    ashtaka_raasi_pindas, ashtaka_graha_pindas, ashtaka_sodhya_pindas = ashtakavarga.sodhaya_pindas(ashtaka_bav, d1_chart_1d)

    vimshottari = horo._get_vimsottari_dhasa_bhukthi(dob_tuple, TOB_TUPLE, place)
    all_available_dhasa = _invoke_available_dhasa_methods(horo, dob_tuple, TOB_TUPLE, place)

    yogas_all, yogas_found, yogas_possible = yoga.get_yoga_details_for_all_charts(jd, place)
    doshas = dosha.get_dosha_details(jd, place)
    predictions_general = general.get_prediction_details(jd, place)
    life_span_range, life_span_group = longevity.life_span_range(jd, place)

    report = {
        "input": {
            "name": NAME,
            "date_of_birth": f"{DOB.year:04d}-{DOB.month:02d}-{DOB.day:02d}",
            "time_of_birth": TOB_STR,
            "place": PLACE_NAME,
            "resolved_place": {
                "name": place.name,
                "latitude": place.latitude,
                "longitude": place.longitude,
                "timezone": place.timezone,
                "elevation": place.elevation,
            },
        },
        "calendar_information": calendar_info,
        "planetary_positions_d1": d1_positions,
        "house_positions_d1": {
            "bhava_chart": bhava_chart,
            "bhava_chart_info": bhava_chart_info,
            "bhava_ascendant_house": bhava_asc_house,
        },
        "charts": {
            "rasi_d1": divisional_charts.get("D1"),
            "navamsa_d9": divisional_charts.get("D9"),
            "dasamsa_d10": divisional_charts.get("D10"),
            "all_available_divisional_charts": divisional_charts,
            "horoscope_information_all_charts": {
                "horoscope_info": horoscope_info,
                "horoscope_charts": horoscope_charts,
                "horoscope_ascendant_houses": horoscope_asc_houses,
            },
        },
        "vimshottari_dasha": vimshottari,
        "all_available_dasha_calculations": all_available_dhasa,
        "yogas": {
            "all_charts": yogas_all,
            "found_count": yogas_found,
            "possible_count": yogas_possible,
        },
        "doshas": doshas,
        "arudhas": {
            "bhava_arudhas_from_d1": arudhas.bhava_arudhas_from_planet_positions(d1_positions),
            "graha_arudhas_from_d1": arudhas.graha_arudhas_from_planet_positions(d1_positions),
        },
        "ashtakavarga": {
            "binna_ashtaka_varga": ashtaka_bav,
            "samudhaya_ashtaka_varga": ashtaka_sav,
            "prastara_ashtaka_varga": ashtaka_prastara,
            "raasi_pindas": ashtaka_raasi_pindas,
            "graha_pindas": ashtaka_graha_pindas,
            "sodhaya_pindas": ashtaka_sodhya_pindas,
        },
        "shadbala": strength.shad_bala(jd, place),
        "special_lagnas": special_lagnas_by_chart,
        "predictions": {
            "general": predictions_general,
            "longevity": {
                "life_span_range": life_span_range,
                "life_span_group": life_span_group,
            },
        },
        "other_available_horoscope_calculations": {
            "sphutas_by_chart": sphutas_by_chart,
            "ava_saha_yogi_avayogi_by_chart": ava_saha_by_chart,
            "chara_karakas_d1": horo.get_chara_karakas_for_chart(jd, place, divisional_chart_factor=1),
        },
    }
    return _to_serializable(report)


def write_outputs(report: dict[str, Any]) -> None:
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# Full Horoscope Report: {NAME}",
        "",
        "This report was generated using PyJHora repository defaults, built-in location lookup, and existing calculation APIs.",
        "",
    ]
    for section, value in report.items():
        md_lines.append(f"## {section.replace('_', ' ').title()}")
        md_lines.extend(_markdown_for_value(value))
        md_lines.append("")
    MD_OUT.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    utils.set_language(const._DEFAULT_LANGUAGE)
    report = build_report()
    write_outputs(report)
    print(f"Saved {JSON_OUT.resolve()}")
    print(f"Saved {MD_OUT.resolve()}")


if __name__ == "__main__":
    main()
