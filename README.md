# veriFHIR 🔥✅

**veriFHIR** is a tool designed to support the FHIR interoperability community by **assessing the quality of FHIR Implementation Guides (IGs)**. As FHIR IGs become easier to create, ensuring their consistency, accuracy, and adherence to best practices is increasingly important.

**veriFHIR** performs **automated checks by leveraging Large Language Models (LLMs)** to analyze narrative content and provide actionable insights to improve clarity, consistency, and overall quality.

## Getting started 🚀

### Installation

* Make sure Python (version 3.10) is installed on your system.
* Clone the veriFHIR repository from GitHub.
* Navigate into the veriFHIR project directory.
* Install the required dependencies listed in requirements.txt using pip.

### Configuration

veriFHIR requires an [OpenAI API](https://platform.openai.com/api-keys) key to work. 
Follow these steps:
* Create a new .env file by copying the provided [.env_example](./veriFHIR/config/.env_example).
* Replace the placeholder with your OpenAI API key.

### Usage

Once veriFHIR is installed and configured with your OpenAI API key, run the [main.py](./main.py) script to analyze a FHIR Implementation Guide using the command-line interface.

**Command:**
```
python main.py--file "path/to/your/implementation_guide.zip" --output "path/to/output/folder"
```

**Explanation of the parameters:**

* `--file`: Path to the ZIP file containing the entire FHIR Implementation Guide you want to review. Make sure the ZIP includes all parts of the specification.
    * For IGs generated with IG Publisher, this file is usually called `full-ig.zip`.
    * For IGs generated with Simplifier, you should use the guide export function to create the ZIP file.
* `--output`: Path to the folder where the analysis report will be saved.
* `--model` (optional): Name of the OpenAI model to use.
  * The model must support [structured outputs](https://platform.openai.com/docs/guides/structured-outputs).
  * Default value: gpt-4o-mini

After running the command, veriFHIR will generate a report in the specified output folder.

## License 📜

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](./LICENSE) file for details.

## Support 💬

Issues, feature requests, and requests for assistance can be submitted [here](https://github.com/Kereval35/veriFHIR/issues). All submissions will be reviewed.