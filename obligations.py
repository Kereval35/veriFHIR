import argparse
import csv
from pathlib import Path

from veriFHIR.utils.utils import extract_zip
from veriFHIR.ig.fhir_ig import FHIRIG


def get_obligations(ig, output_path, obligation_url = "http://hl7.org/fhir/StructureDefinition/obligation"):
    profiles = [artifact for artifact in ig.get_artifacts_type("StructureDefinition") if artifact.get_content().get("kind") == "resource"]
    obligations = []

    for profile in profiles:
        content = profile.get_content()
        elements = content.get("snapshot", {}).get("element", [])
        for element in elements:
            for ext in element.get("extension", []):
                if ext.get("url")  != obligation_url:
                    continue
                obligation_data = {
                    "profile": profile.get_id(),
                    "path": element.get("path"), 
                    "slice": element.get("sliceName"),
                    "code": None, 
                    "actor": None,
                }
                details = {}
                for sub_ext in ext.get("extension", []):
                    url = sub_ext.get("url")
                    value = next(
                        (v for k, v in sub_ext.items() if k.startswith("value")),
                        None
                    )
                    details[url] = value
                obligation_data["code"] = details.get("code")
                obligation_data["actor"] = details.get("actor").split("/")[-1] #type: ignore
                obligations.append(obligation_data)

    output_file = Path(output_path, f"obligations_{ig.get_metadata().get_name()}.csv")
    fieldnames = ["profile", "path", "slice", "code", "actor"]
    with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(obligations)
    return output_file


def main():
    parser = argparse.ArgumentParser(description="obligations extraction", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--file", type=str, required=True, help="Full IG ZIP file path (type: str)")
    parser.add_argument("--output", type=str, required=True, help="Output path (type: str)")
    args = parser.parse_args()

    ig_dir, ig_path = extract_zip(args.file)
    ig = FHIRIG(ig_path)
    output_file = get_obligations(ig, args.output)
    print(f"File saved at: {output_file}")


if __name__ == "__main__":
    main()

# python obligations.py --file "./test/eps.zip" --output "./test"