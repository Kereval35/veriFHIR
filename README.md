<p align="center">
  <img src="veriFHIR.png" alt="Logo" width="200">
</p>

**VeriFHIR** is a tool designed to support the FHIR interoperability community by **assessing the quality of FHIR Implementation Guides (IGs)**. As FHIR IGs become easier to create, ensuring their consistency, accuracy, and adherence to best practices is increasingly important.

**VeriFHIR** performs **automated checks by leveraging Large Language Models (LLMs)** to analyze narrative content and provide actionable insights to improve clarity, consistency, and overall quality.

# Getting started 🚀

## Installation

* Make sure Python (version 3.10) is installed on your system.
* Clone the VeriFHIR repository from GitHub.
* Navigate into the VeriFHIR project directory.
* Install the required dependencies listed in requirements.txt using pip.

## Configuration

VeriFHIR requires an [OpenAI API](https://platform.openai.com/api-keys) key to work. 
Follow these steps:
* Create a new .env file by copying the provided [.env_example](./veriFHIR/config/.env_example).
* Replace the placeholder with your OpenAI API key.

## Usage

Once VeriFHIR is installed and configured with your OpenAI API key, run the [main.py](./main.py) script to analyze a FHIR Implementation Guide using the command-line interface.

**Command:**
```
python main.py --file "path/to/your/implementation_guide.zip" --output "path/to/output/folder"
```

**Explanation of the parameters:**

* `--file`: Path to the ZIP file containing the entire FHIR Implementation Guide you want to review. Make sure the ZIP includes all parts of the specification.
    * For IGs generated with IG Publisher, this file is usually called `full-ig.zip`.
    * For IGs generated with Simplifier, you should use the guide export function to create the ZIP file.
* `--output`: Path to the folder where the analysis report will be saved.
* `--model` (optional): Name of the OpenAI model to use.
  * The model must support [structured outputs](https://platform.openai.com/docs/guides/structured-outputs).
  * Default value: gpt-4o-mini
* `--check-format`: Check artifacts naming rules according to [ANS naming rules](https://ansforge.github.io/IG-documentation/main/ig/mod_bonnes_pratiques.html#r%C3%A8gles-de-nommage-des-ressources-de-conformit%C3%A9).
* `--check-clarity`: Check for ambiguous or unclear wording. This may produce a large number of findings depending on the text, including minor or subjective issues.

After running the command, VeriFHIR will generate a report in the specified output folder. An [example report](https://kereval35.github.io/veriFHIR/example/example_report.html) is available in the [example](./example) folder.

### Obligations extraction script

In addition to the main VeriFHIR workflow, the repository includes a script to extract FHIR obligations from IG. It parses StructureDefinition resources and retrieves elements annotated with the [FHIR obligation extension](http://hl7.org/fhir/StructureDefinition/obligation). The extracted data includes the profile, element path, slice name, obligation code, and actor, and is exported as a CSV file for further analysis or reuse.

```
python obligations.py --file "path/to/your/implementation_guide.zip" --output "path/to/output/folder"
```

# License 📜

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](./LICENSE) file for details.

# Support 💬

Issues, feature requests, and requests for assistance can be submitted [here](https://github.com/Kereval35/veriFHIR/issues). All submissions will be reviewed.