import argparse

from veriFHIR import FHIRIG
from veriFHIR import CheckerManager
from veriFHIR import PageTypeChecker, AllPagesChecker, TextChecker, ArtifactsChecker, RefsChecker, AmbiguousWordingChecker
from veriFHIR.utils.utils import extract_zip


def main():
    parser = argparse.ArgumentParser(description="veriFHIR project tools", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--file", type=str, required=True, help="Full IG ZIP file path (type: str)")
    parser.add_argument("--output", type=str, required=True, help="Output path (type: str)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model name (type: str)")
    parser.add_argument("--check-format", action="store_true", help="Check artifacts naming rules according to https://ansforge.github.io/IG-documentation/main/ig/mod_bonnes_pratiques.html#r%C3%A8gles-de-nommage-des-ressources-de-conformit%C3%A9")
    parser.add_argument("--check-clarity", action="store_true", help="Check ambiguous wording")
    args = parser.parse_args()

    print("Starting the review")
    print("...")
    ig_dir, ig_path = extract_zip(args.file)
    ig = FHIRIG(ig_path)
    manager = CheckerManager()
    manager.register(PageTypeChecker(ig, args.model))
    manager.register(RefsChecker(ig))
    manager.register(AllPagesChecker(ig, args.model))
    manager.register(TextChecker(ig, args.model))
    if args.check_clarity:
        manager.register(AmbiguousWordingChecker(ig, args.model))
    manager.register(ArtifactsChecker(ig, check_format=args.check_format))
    report = manager.check()
    output_file = report.write(args.output, ig.get_metadata())
    ig_dir.cleanup()
    print(f"Repport saved at: {output_file}")


if __name__ == "__main__":
    main()
