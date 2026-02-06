import argparse

from veriFHIR import FHIRIG
from veriFHIR import CheckerManager
from veriFHIR import PageTypeChecker, AllPagesChecker, TextChecker, ArtifactsChecker
from veriFHIR.utils.utils import extract_zip


def main():
    parser = argparse.ArgumentParser(description="veriFHIR project tools", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--file", type=str, required=True, help="Full IG ZIP file path (type: str)")
    parser.add_argument("--output", type=str, required=True, help="Output path (type: str)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model name (type: str)")
    args = parser.parse_args()

    print("Starting the review")
    print("...")
    ig_dir, ig_path = extract_zip(args.file)
    ig = FHIRIG(ig_path)
    manager = CheckerManager()
    manager.register(PageTypeChecker(ig, args.model))
    manager.register(AllPagesChecker(ig, args.model))
    manager.register(TextChecker(ig, args.model))
    manager.register(ArtifactsChecker(ig))
    report = manager.check()
    output_file = report.write(args.output, ig.get_metadata())
    ig_dir.cleanup()
    print(f"Repport saved at: {output_file}")


if __name__ == "__main__":
    main()
