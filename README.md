# ExitWP for Hugo

## Convert WordPress and Squarespace exports to the [Hugo static site generator](https://gohugo.io/)

This is an updated version of the ExitWP tool, originally created by Thomas Frössman for Jekyll and later adapted for Hugo by Arjan Wooning.

For a detailed guide and background information, visit [Arjan Wooning's website](https://arjan.wooning.cz/conversion-tools-from-wordpress-to-hugo/#final-solution-exitwp-for-hugo).

ExitWP is a tool designed to simplify the migration process from one or more WordPress blogs, or other blogs/websites exported to the WordPress XML format, to the [Hugo static site generator](https://gohugo.io/). It aims to convert as much information as possible from the WordPress export, with options to filter the converted data.
[SquareSpace](https://squarespace.com/) also offers the option to [export your site as WordPress formatted XML file(s)](https://support.squarespace.com/hc/en-us/articles/206566687-Exporting-your-site?platform=v6&websiteId=5974c4a71b631b9a769048c6).

## Features

- Converts WordPress export XML to Hugo-compatible Markdown or HTML
- Downloads and processes images within posts
- Supports inclusion of comments from WordPress posts
- Handles tags and categories for Hugo
- Flexible configuration options via `config.yaml`

Please refer to the [Release notes](RELEASE_NOTES.md) (RELEASE_NOTES.md) for an overview of changes and updates.

## Getting Started

1. Clone the repository: `git clone https://github.com/wooni005/exitwp-for-hugo.git`
2. Export your WordPress blog(s) using the WordPress exporter (Tools > Export in WordPress admin). Other website hosting sites, like [SquareSpace](https://squarespace.com/) also offer the option to export your site as WordPress formatted XML file(s).
3. Place all WordPress XML files in the `wordpress-xml` directory
4. Configure the tool by editing `config.yaml`
5. Run the converter: `python3 exitwp.py`
6. Optionally, if the script runs into issues, or the output does not appear to be correct, run `xmllint` [part of Libxml2](https://en.wikipedia.org/wiki/Libxml2) on your export file(s) and fix any errors.
7. Your converted blog(s) will be in separate directories under the `build` directory, specified in `config.yaml`.

## Dependencies

- Python 3.x
- markdownify
- PyYAML
- Beautiful Soup 4

## Installing Dependencies

```bash
pip3 install -r requirements.txt
```

## Configuration

Refer to the `config.yaml` file for all configurable options. Key settings include:

- `wp_exports`: Directory containing WordPress export XML files
- `build_dir`: Target directory for output
- `download_images`: Whether to download and relocate images
- `include_comments`: Option to include comments in the exported content
- `target_format`: Choose between 'markdown' or 'html' output
- `image_settings`: Configure image processing behavior

## Usage

Basic usage:

```bash
python3 exitwp.py
```

For verbose output:

```bash
python3 exitwp.py -v
```

## Known Issues and Limitations

- Potential issues with non-UTF-8 encoded WordPress dump files
- Image downloading may fail for some URLs due to various reasons (404 errors, timeouts, etc.)

## Support

This tool is not actively maintained. For support or custom modifications, consider using AI chatbots like ChatGPT or Claude.

## Contributing

If you've made significant improvements to the tool, feel free to submit a pull request.
