# Changelog and Release Notes

# August 2024

## exitwp.py

### Major Changes
- Replaced html2text_file with markdownify for HTML to Markdown conversion
- Added support for downloading and processing images within posts
- Implemented comment extraction and inclusion in the output
- Added support for tags and categories handling
- Improved error handling and logging

### New Features
- Image processing: Downloads images, saves them locally, and updates image URLs in the content
- Comment handling: Extracts and includes comments in the output markdown files
- Tags and categories: Properly handles WordPress tags and categories, mapping them to Hugo format
- Timezone handling: Added support for CET timezone

### Improvements
- Enhanced YAML header generation for Hugo compatibility
- Improved date parsing and handling
- Better error logging and verbose output options
- Refactored code for better readability and maintainability

### Bug Fixes
- Fixed issues with Unicode handling
- Addressed potential errors in parsing XML and HTML content

## config.yaml

### New Options
- Added `tags_label` option to specify the label for tags/categories in the output
- Introduced `include_comments` option to control whether comments are included in the export

### Changes
- Refined `taxonomies` configuration to better handle tags and categories
- Updated `body_replace` patterns for improved content transformation

### Improvements
- Added more detailed comments and explanations for configuration options

## Overall Improvements

1. Better Hugo Compatibility: The updated script now generates output more closely aligned with Hugo's expectations.
2. Enhanced Image Handling: Improved downloading and processing of images within posts.
3. Comment Support: Added the ability to include WordPress comments in the exported content.
4. Improved Taxonomy Handling: Better management of tags and categories for Hugo.
5. More Flexible Configuration: Additional options in config.yaml for finer control over the export process.

## Upgrade Notes

When upgrading to this new version:

1. Review the new configuration options in config.yaml and adjust as needed for your use case.
2. Be aware of the change from html2text to markdownify for HTML to Markdown conversion.
3. Test the script with a small subset of your content first to ensure compatibility with your specific WordPress export.
4. Pay attention to the new image handling and comment inclusion features, adjusting settings as necessary.

This update significantly improves the WordPress to Hugo migration process, offering more features and better compatibility with Hugo's content structure.
