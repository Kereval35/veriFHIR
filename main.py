import argparse

from veriFHIR.ig.fhir_ig import FHIRIG
from veriFHIR.checkers.checker_manager import CheckerManager
from veriFHIR.checkers.checkers import PageTypeChecker, AllPagesChecker, TextChecker, ArtifactsChecker, ComparativeArtifactsChecker
from veriFHIR.utils.utils import extract_zip


def main():
    parser = argparse.ArgumentParser(description="veriFHIR project tools")
    parser.add_argument("--file", type=str, required=True, help="Full IG ZIP file path")
    parser.add_argument("--output", type=str, required=True, help="Output path")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model name")
    args = parser.parse_args()

    print("Starting the review")
    ig_dir, ig_path = extract_zip(args.file)
    ig = FHIRIG(ig_path)
    manager = CheckerManager()
    #manager.register(PageTypeChecker(ig, args.model))
    #manager.register(AllPagesChecker(ig, args.model))
    #manager.register(TextChecker(ig, args.model))
    #manager.register(ArtifactsChecker(ig))
    manager.register(ComparativeArtifactsChecker(ig, args.model))
    report = manager.check()
    output_file = report.write(args.output, ig.get_metadata())
    ig_dir.cleanup()
    print(f"Repport saved at: {output_file}")


if __name__ == "__main__":
    main()
