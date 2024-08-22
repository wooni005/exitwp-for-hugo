#!/usr/bin/env python3

import codecs
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, tzinfo
from glob import glob
from urllib.request import urlretrieve
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import ElementTree, TreeBuilder, XMLParser
from urllib.error import HTTPError, URLError
import socket

import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify as md

'''
exitwp - Wordpress xml exports to Hugo blog format conversion

Tested with Wordpress 3.3.1 and hugo v0.131.0

'''
######################################################
# Configration
######################################################
config = yaml.safe_load(open('config.yaml', 'r'))
wp_exports = config['wp_exports']
build_dir = config['build_dir']
download_images = config['download_images']
include_comments = config['include_comments']
target_format = config['target_format']
taxonomy_filter = set(config['taxonomies']['filter'])
taxonomy_entry_filter = config['taxonomies']['entry_filter']
taxonomy_name_mapping = config['taxonomies']['name_mapping']
# NOTE: categories label in the taxonomy is overwritten by the tags_label below!
tags_label = config.get('tags_label', 'categories')
item_type_filter = set(config['item_type_filter'])
item_field_filter = config['item_field_filter']
date_fmt = config['date_format']
body_replace = config['body_replace']
verbose = config['verbose']

image_config = config.get('image_settings', {})
EXCLUDED_URL_PARTS = image_config.get('excluded_url_parts', [])
INCLUDED_DOMAINS = image_config.get('included_domains', [])
DEFAULT_IMAGE_VALIDITY = image_config.get('default_image_validity', True)
IMAGE_NOT_FOUND_ICON = image_config.get('not_found_icon', '/icons/question-warning.svg')
DEFAULT_DOWNLOAD_TIMEOUT = image_config.get('download_timeout', 3)

# Global dictionary to track image sources and their local filenames
image_sources = {}

# Time definitions
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# Logging
def log(msg):
    if verbose:
        print(msg)

if include_comments:
    log('Comments will be included in the export.')
else:
    log('Comments will not be included in the export.')

# UTC support
class UTC(tzinfo):
    """UTC."""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return 'UTC'

    def dst(self, dt):
        return ZERO

# CET Timezone (Adapt to your own timezone)
class CET(tzinfo):
    def utcoffset(self, dt):
        return timedelta(hours=1)

    def tzname(self, dt):
        return "CET"

    def dst(self, dt):
        return timedelta(0)

class ns_tracker_tree_builder(TreeBuilder):

    def __init__(self):
        TreeBuilder.__init__(self)
        self.namespaces = {}

    def start_ns(self, prefix, uri):
        self.namespaces[prefix] = '{' + uri + '}'

def html2fmt(html, target_format):
    if target_format == 'html':
        return html
    else:
        # Use markdownify to convert HTML to Markdown
        return md(html, heading_style="ATX", bullets="-*+")

def is_valid_image(url):
    # Exclude URLs containing any of the parts in EXCLUDED_URL_PARTS
    if any(part in url for part in EXCLUDED_URL_PARTS):
        return False

    # Exclude small tracking pixels (often 1x1)
    if re.search(r'(width|height)=["\']?1["\']?', url):
        return False

    # Include images from specified domains
    if any(domain in url for domain in INCLUDED_DOMAINS):
        return True

    # If no exclusion condition is met and it's not from an included domain,
    # you can decide to either include or exclude it by default
    return DEFAULT_IMAGE_VALIDITY


def download_image(url, local_path, timeout=DEFAULT_DOWNLOAD_TIMEOUT):
    if not is_valid_image(url):
        log(f"Skipping invalid image: {url}")
        return False

    if os.path.exists(local_path):
        print(f'Image already exists: {local_path}')
        return False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, open(local_path, 'wb') as out_file:
            out_file.write(response.read())
        log(f"Successfully downloaded: {url}")
        return True
    except (HTTPError, URLError, socket.timeout) as e:
        print(f"Error downloading {url}: {str(e)}")
    except Exception as e:
        print(f"Unexpected error when downloading {url}: {str(e)}")
    return False

def parse_wp_xml(file):
    tree_builder = ns_tracker_tree_builder()
    parser = XMLParser(target=tree_builder)
    tree = ElementTree()
    log('reading: ' + wpe)
    root = tree.parse(file, parser)
    ns = tree_builder.namespaces
    ns[''] = ''

    c = root.find('channel')

    def parse_header():
        return {
            'title': str(c.find('title').text),
            'link': str(c.find('link').text),
            'description': str(c.find('description').text)
        }

    def parse_items():
        export_items = []
        xml_items = c.findall('item')
        for i in xml_items:
            taxanomies = i.findall('category')
            export_taxanomies = {}
            tags = ['pre-2010']  # New list to store tags
            for tax in taxanomies:
                if 'domain' not in tax.attrib:
                    continue
                t_domain = str(tax.attrib['domain'])
                t_entry = str(tax.attrib.get('nicename', tax.text.strip()))
                if t_domain == 'category':  # If it's a category, add it to tags
                    tags.append(t_entry)
                elif (not (t_domain in taxonomy_filter) and
                      not (t_domain in taxonomy_entry_filter and
                           taxonomy_entry_filter[t_domain] == t_entry)):
                    if t_domain not in export_taxanomies:
                        export_taxanomies[t_domain] = []
                    export_taxanomies[t_domain].append(t_entry)

            def gi(q, unicode_wrap=True, empty=False):
                namespace = ''
                tag = q
                if q.find(':') > 0:
                    namespace, tag = q.split(':', 1)
                try:
                    result = i.find('.//' + ns[namespace] + tag).text
                    if result is None:
                        return '' if empty else None
                except AttributeError:
                    return '' if empty else None
                if unicode_wrap:
                    result = str(result)
                return result

            body = gi('content:encoded')
            for key in body_replace:
                body = re.sub(key, body_replace[key], body)

            # Parse HTML content
            soup_body = BeautifulSoup(body, 'html.parser')

            # Extract image sources from body only
            img_srcs = []
            for img in soup_body.find_all('img'):
                if 'src' in img.attrs:
                    img_src = img['src']
                    if is_valid_image(img_src):
                        img_srcs.append(img_src)

            # Remove duplicates
            img_srcs = list(set(img_srcs))

            # Extract comments
            comments = []
            if include_comments:
                comment_elements = i.findall('.//wp:comment', namespaces={'wp': 'http://wordpress.org/export/1.2/'})
                log(f"Number of comment elements found: {len(comment_elements)}")
                for comment in comment_elements:
                    comment_data = {
                        'author': comment.find('wp:comment_author', namespaces={'wp': 'http://wordpress.org/export/1.2/'}).text.strip(),
                        'date': comment.find('wp:comment_date', namespaces={'wp': 'http://wordpress.org/export/1.2/'}).text.strip(),
                        'content': comment.find('wp:comment_content', namespaces={'wp': 'http://wordpress.org/export/1.2/'}).text.strip()
                    }
                    comments.append(comment_data)
                log(f"Number of comments extracted: {len(comments)}")

            export_item = {
                'title': gi('title'),
                'link': gi('link'),
                'author': gi('dc:creator'),
                'date': gi('wp:post_date_gmt'),
                'slug': gi('wp:post_name'),
                'status': gi('wp:status'),
                'type': gi('wp:post_type'),
                'wp_id': gi('wp:post_id'),
                'parent': gi('wp:post_parent'),
                'taxanomies': export_taxanomies,
                'tags': tags,  # Add tags to the export item
                'body': body,
                'img_srcs': img_srcs,
                'comments': gi('wp:comment_status') == u'open',
                'comments': comments # if include_comments else []  # Only include comments if include_comments is True
            }

            export_items.append(export_item)

        return export_items

    return {
        'header': parse_header(),
        'items': parse_items(),
    }

def write_hugo(data, target_format):

    if verbose:
        log('writing..')
    else:
        sys.stdout.write('writing')
    item_uids = {}
    attachments = {}

    def get_blog_path(data, path_infix='hugo'): #AW!! Changed jekyll path into hugo
        name = data['header']['link']
        name = re.sub('^https?', '', name)
        name = re.sub('[^A-Za-z0-9_.-]', '', name)
        return os.path.normpath(build_dir + '/' + path_infix + '/' + name)

    blog_dir = get_blog_path(data)

    def get_full_dir(dir):
        full_dir = os.path.normpath(blog_dir + '/' + dir)
        if (not os.path.exists(full_dir)):
            os.makedirs(full_dir)
        return full_dir

    def open_file(file):
        f = codecs.open(file, 'w', encoding='utf-8')
        return f

    def get_item_uid(item, date_prefix=False, namespace=''):
        result = None
        if namespace not in item_uids:
            item_uids[namespace] = {}

        if item['wp_id'] in item_uids[namespace]:
            result = item_uids[namespace][item['wp_id']]
        else:
            uid = []
            if (date_prefix):
                dt = datetime.strptime(item['date'], date_fmt)
                uid.append(dt.strftime('%Y-%m-%d'))
                uid.append('-')
            s_title = item['slug']
            if s_title is None or s_title == '':
                s_title = item['title']
            if s_title is None or s_title == '':
                s_title = 'untitled'
            s_title = s_title.replace(' ', '_')
            s_title = re.sub('[^a-zA-Z0-9_-]', '', s_title)
            uid.append(s_title)
            fn = ''.join(uid)
            n = 1
            while fn in item_uids[namespace]:
                n = n + 1
                fn = ''.join(uid) + '_' + str(n)
                item_uids[namespace][i['wp_id']] = fn
            result = fn
        return result

    def get_item_path(item, dir=''):
        full_dir = get_full_dir(dir)
        filename_parts = [full_dir, '/']
        filename_parts.append(item['uid'])
        if item['type'] == 'page':
            if (not os.path.exists(''.join(filename_parts))):
                os.makedirs(''.join(filename_parts))
            filename_parts.append('/index')
        filename_parts.append('.')
        # Determine the file extension based on target_format
        extension = 'md' if target_format.lower() == 'markdown' else target_format
        filename_parts.append(extension)
        return ''.join(filename_parts)

    def get_attachment_path_original(src, dir, dir_prefix='images'):
        try:
            files = attachments[dir]
        except KeyError:
            attachments[dir] = files = {}

        try:
            filename = files[src]
        except KeyError:
            file_root, file_ext = os.path.splitext(os.path.basename(urlparse(src)[2]))
            file_infix = 1
            if file_root == '':
                file_root = '1'
            current_files = files.values()
            maybe_filename = file_root + file_ext
            while maybe_filename in current_files:
                maybe_filename = file_root + '-' + str(file_infix) + file_ext
                file_infix = file_infix + 1
            files[src] = filename = maybe_filename

        target_dir = os.path.normpath(blog_dir + '/' + dir_prefix + '/' + dir)
        target_file = os.path.normpath(target_dir + '/' + filename)

        if (not os.path.exists(target_dir)):
            os.makedirs(target_dir)

        return target_file, f'/{dir_prefix}/{dir}/{filename}'

    image_counter = {}

    def get_attachment_path(src, item_uid, item_type):
        if item_type != 'post':
            return get_attachment_path_original(src, item_uid)

        parsed_url = urlparse(src)
        file_name = os.path.basename(parsed_url.path)
        if file_name == '':
            file_name = '1.jpg'  # Default name if no filename is found

        base_name, ext = os.path.splitext(file_name)

        target_dir = os.path.normpath(blog_dir + '/images/posts')
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        # First, check if the file already exists in the target directory
        if os.path.exists(os.path.join(target_dir, file_name)):
            target_file = os.path.normpath(target_dir + '/' + file_name)
            relative_path = '/images/posts/' + file_name
            return target_file, relative_path

        if src in image_sources:
            # We've seen this exact URL before, use the same local filename
            return image_sources[src]

        counter = 0
        while True:
            if counter == 0:
                new_file_name = file_name
            else:
                new_file_name = f"{base_name}-{counter}{ext}"

            target_file = os.path.normpath(target_dir + '/' + new_file_name)
            relative_path = '/images/posts/' + new_file_name

            if not os.path.exists(target_file):
                # This filename is not used, we can use it
                image_sources[src] = (target_file, relative_path)
                return target_file, relative_path

            # If we're here, the filename exists.
            # If it's for the same source URL, we can reuse it
            if any(existing_src for existing_src, (existing_file, _) in image_sources.items()
                   if existing_file == target_file and existing_src == src):
                return target_file, relative_path

            # If we're here, the filename exists but for a different source
            # Try the next counter
            counter += 1

    def process_image(soup, img_tag, fn, item_uid, item_type):
        if not download_images:
            return  # Skip all image processing if download_images is False

        original_src = img_tag.get('src', '')
        if not original_src or not is_valid_image(original_src):
            return

        full_img_url = urljoin(data['header']['link'], original_src)
        local_path, relative_path = get_attachment_path(full_img_url, item_uid, item_type)

        if os.path.exists(local_path):
            log(f"Using existing local copy for {original_src}")
            img_tag['src'] = relative_path
        elif full_img_url != IMAGE_NOT_FOUND_ICON:
            if download_image(full_img_url, local_path):
                log(f"Downloaded image: {original_src}")
                img_tag['src'] = relative_path
            else:
                log(f"Error: Image not found online: {original_src}")
                img_tag['src'] = IMAGE_NOT_FOUND_ICON
        else:
            log(f"Error: Invalid image source: {original_src}")
            img_tag['src'] = IMAGE_NOT_FOUND_ICON

        img_tag['title'] = original_src

        # Preserve the original link destination
        parent_a = img_tag.find_parent('a')
        if parent_a and 'href' in parent_a.attrs:
            parent_a['href'] = parent_a['href']  # Keep the original href

    for i in data['items']:
        skip_item = None

        for field, value in item_field_filter.items():
            if(i[field] == value):
                skip_item = value
                break

        if(skip_item):
            log('  skipped(field=' + skip_item + ')/' + i['wp_id'] + ': ' + i['title'])
            continue

        if not verbose:
            sys.stdout.write('.')
            sys.stdout.flush()
        out = None

        item_url = urlparse(i['link'])
        yaml_header = {
            'title': i['title'],
            'url': item_url.path,
            # 'author': i['author'],
        }

        # Handle the date
        date_str = i.get('date')
        if date_str:
            try:
                # Parse the date string and set the timezone to CET
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                parsed_date = parsed_date.replace(tzinfo=CET())
                yaml_header['date'] = parsed_date
            except ValueError:
                log(f"Warning: Invalid date format for item {i['wp_id']}: {date_str}. Date will be left empty.")
        else:
            log(f"Info: No date found for item {i['wp_id']}. Date will be left empty.")

        # if i['status'] == u'publish':
        #     yaml_header['draft'] = False

        log(f"Processing item: {i['title']}")
        log(f"Number of comments: {len(i['comments'])}")

        if i['type'] == 'post':
            i['uid'] = get_item_uid(i, date_prefix=True)
            fn = get_item_path(i, dir='posts')
            out = open_file(fn)
            yaml_header['type'] = 'post'
        elif i['type'] == 'page':
            i['uid'] = get_item_uid(i)
            # Chase down parent path, if any
            parentpath = ''
            item = i
            while item['parent'] != '0':
                item = next((parent for parent in data['items']
                             if parent['wp_id'] == item['parent']), None)
                if item:
                    parentpath = get_item_uid(item) + '/' + parentpath
                else:
                    break
            fn = get_item_path(i, parentpath)
            out = open_file(fn)
            yaml_header['type'] = 'page'
        elif i['type'] in item_type_filter:
            log('  skipped(type=' + i['type'] + ')/' + i['wp_id']+ ': ' + i['title'])
            continue
        else:
            print('Unknown item type :: ' + i['type'])
            continue

        if download_images:
            soup = BeautifulSoup(i['body'], 'html.parser')
            for img in soup.find_all('img'):
                process_image(soup, img, fn, i['uid'], i['type'])
            i['body'] = str(soup)

        if out is not None:
            def toyaml(data):
                return yaml.safe_dump(data, allow_unicode=True,
                                      default_flow_style=False)

            # Add tags to the YAML header
            if i['tags']:
                yaml_header[tags_label] = i['tags']

            tax_out = {}
            for taxonomy in i['taxanomies']:
                if taxonomy != 'category':  # Skip 'category' as we're using it for tags
                    for tvalue in i['taxanomies'][taxonomy]:
                        t_name = taxonomy_name_mapping.get(taxonomy, taxonomy)
                        if t_name not in tax_out:
                            tax_out[t_name] = []
                        if tvalue in tax_out[t_name]:
                            continue
                        tax_out[t_name].append(tvalue)

            out.write('---\n')
            if len(yaml_header) > 0:
                out.write(toyaml(yaml_header))
            if len(tax_out) > 0:
                out.write(toyaml(tax_out))

            out.write('---\n\n')
            try:
                markdown_content = html2fmt(i['body'], target_format)
                out.write(markdown_content)
            except Exception as e:
                print(f'\nParse error on: {i["title"]}. Error: {str(e)}')

            # Add comments
            if include_comments and i['comments']:
                out.write('\n---\n\n### Comments\n\n')
                for comment in i['comments']:
                    out.write(f"> Author: {comment['author']}<br>\n")
                    out.write(f"> Date: {comment['date']}\n\n")
                    content = comment['content'].replace('\n', '\n\n')  # Ensure proper line breaks in Markdown
                    out.write(f"{content}\n\n")

            out.close()
            log('  written/' + i['wp_id'] + ': ' + i['title'])

    print('\n')

for arg in range(1, len(sys.argv)):
    if sys.argv[arg] == '-v':
        verbose = True
    elif sys.argv[arg] == '-h':
        print('''
usage: {} [-h(elp)] [-v(erbose)]

Options:
  -h    Show this help message and exit
  -v    Enable verbose output

Configuration:
  All major settings are configured in the 'config.yaml' file.
  Key settings include:

  - wp_exports: Directory containing WordPress export XML files
  - build_dir: Target directory for output
  - download_images: Whether to download and relocate images
  - image_settings: Configure image processing behavior

  Image Settings Example:
    image_settings:
      excluded_url_parts:
        - 'ads.example.com'
        - 'tracking.example.com'
      included_domains:
        - 'images.mysite.com'
        - 'cdn.mysite.com'
      default_image_validity: true

    Set default_image_validity to true to process all images except those
    explicitly excluded, or false to process only images from included_domains.

  For more detailed configuration options, please refer to the comments
  in the config.yaml file.
'''.format(sys.argv[0]))
        sys.exit(0)
print('starting..')
wp_exports = glob(wp_exports + '/*.xml')
for wpe in wp_exports:
    data = parse_wp_xml(wpe)
    write_hugo(data, target_format)

print('done')
