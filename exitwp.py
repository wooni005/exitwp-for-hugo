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

import yaml
from bs4 import BeautifulSoup

from html2text import html2text_file

'''
exitwp - Wordpress xml exports to Hugo blog format conversion

Tested with Wordpress 3.3.1 and hugo 0.69

'''
######################################################
# Configration
######################################################
config = yaml.safe_load(open('config.yaml', 'r'))
wp_exports = config['wp_exports']
build_dir = config['build_dir']
download_images = config['download_images']
target_format = config['target_format']
taxonomy_filter = set(config['taxonomies']['filter'])
taxonomy_entry_filter = config['taxonomies']['entry_filter']
taxonomy_name_mapping = config['taxonomies']['name_mapping']
item_type_filter = set(config['item_type_filter'])
item_field_filter = config['item_field_filter']
date_fmt = config['date_format']
body_replace = config['body_replace']
verbose = config['verbose']


# Time definitions
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# Logging
def log(msg):
    if verbose:
        print(msg)

# UTC support
class UTC(tzinfo):
    """UTC."""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return 'UTC'

    def dst(self, dt):
        return ZERO

class ns_tracker_tree_builder(TreeBuilder):

    def __init__(self):
        TreeBuilder.__init__(self)
        self.namespaces = {}

    def start_ns(self, prefix, uri):
        self.namespaces[prefix] = '{' + uri + '}'

def html2fmt(html, target_format):
    #   html = html.replace("\n\n", '<br/><br/>')
    #   html = html.replace('<pre lang="xml">', '<pre lang="xml"><![CDATA[')
    #   html = html.replace('</pre>', ']]></pre>')
    if target_format == 'html':
        return html
    else:
        return html2text_file(html, None)


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
            for tax in taxanomies:
                if 'domain' not in tax.attrib:
                    continue
                t_domain = str(tax.attrib['domain'])
                t_entry = str(tax.text)
                if (not (t_domain in taxonomy_filter) and
                    not (t_domain
                         in taxonomy_entry_filter and
                         taxonomy_entry_filter[t_domain] == t_entry)):
                    if t_domain not in export_taxanomies:
                        export_taxanomies[t_domain] = []
                    export_taxanomies[t_domain].append(t_entry)

            def gi(q, unicode_wrap=True, empty=False):
                namespace = ''
                tag = ''
                if q.find(':') > 0:
                    namespace, tag = q.split(':', 1)
                else:
                    tag = q
                try:
                    result = i.find(ns[namespace] + tag).text
                    #print(result.encode('utf-8'))
                except AttributeError:
                    result = 'No Content Found'
                    if empty:
                        result = ''
                if unicode_wrap:
                    result = str(result)
                return result

            body = gi('content:encoded')
            for key in body_replace:
                # body = body.replace(key, body_replace[key])
                body = re.sub(key, body_replace[key], body)

            img_srcs = []
            if body is not None:
                try:
                    soup = BeautifulSoup(body, features="lxml")
                    img_tags = soup.find_all('img')
                    for img in img_tags:
                        img_srcs.append(img['src'])
                except:
                    print('could not parse html: ' + body)
            # print(img_srcs)

            excerpt = gi('excerpt:encoded', empty=True)

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
                'comments': gi('wp:comment_status') == u'open',
                'taxanomies': export_taxanomies,
                'body': body,
                'excerpt': excerpt,
                'img_srcs': img_srcs
            }
            log('  item/' + export_item['wp_id'] + ': ' + export_item['title'])
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
        filename_parts.append(target_format)
        return ''.join(filename_parts)

    def get_attachment_path(src, dir, dir_prefix='images'):
        try:
            files = attachments[dir]
        except KeyError:
            attachments[dir] = files = {}

        try:
            filename = files[src]
        except KeyError:
            file_root, file_ext = os.path.splitext(os.path.basename(
                urlparse(src)[2]))
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

        # if src not in attachments[dir]:
        #     print(target_name)
        return target_file

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

        item_url = urlparse(i['link'])        # AW!!: Store item url for later url path relative
        yaml_header = {
            'title': i['title'],
            'url': item_url.path,             # AW!!: Renamed: link (Jekykll) -> url and and make url path relative
            'author': i['author'],
            'date': datetime.strptime(
                i['date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC())
            #'slug': i['slug'],               # AW!!: can be used
            #'wordpress_id': int(i['wp_id']), # AW!!: not used
            #'comments': i['comments'],       # AW!!: Via Disqus
        }
        #if len(i['excerpt']) > 0:
        #    yaml_header['excerpt'] = i['excerpt'] # AW!!: can be used
        if i['status'] == u'publish':
            yaml_header['draft'] = False
        #else:
        #    yaml_header['draft'] = True

        if i['type'] == 'post':
            i['uid'] = get_item_uid(i, date_prefix=True)
            fn = get_item_path(i, dir='_posts')
            out = open_file(fn)
            yaml_header['type'] = 'post'      # AW!!: Changed from layout into type
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
            yaml_header['type'] = 'page'      # AW!!: Changed from layout into type
        elif i['type'] in item_type_filter:
            log('  skipped(type=' + i['type'] + ')/' + i['wp_id']+ ': ' + i['title'])
            pass
        else:
            print('Unknown item type :: ' + i['type'])

        if download_images:
            for img in i['img_srcs']:
                comp = urllib.parse.urlparse(img)
                if comp[1] == '':
                    comp._replace(netloc = data['header']['link'])
                newurl = urllib.parse.urlunparse(comp)
                try:
                    urlretrieve(newurl,get_attachment_path(img, i['uid']))
                except:
                    print( f'\n unable to download {newurl}')

        if out is not None:
            def toyaml(data):
                return yaml.safe_dump(data, allow_unicode=True,
                                      default_flow_style=False)

            tax_out = {}
            for taxonomy in i['taxanomies']:
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
                out.write(html2fmt(i['body'], target_format))
            except:
                print('\n Parse error on: ' + i['title'])

            out.close()
            log('  written/' + i['wp_id'] + ': ' + i['title'])
    print('\n')

for arg in range(1, len(sys.argv)):
    if sys.argv[arg] == '-v':
        verbose = True
    elif sys.argv[arg] == '-h':
        print('usage: ' + sys.argv[0] + ' [-h(elp)] [-v(erbose)]')
        sys.exit(0)
print('starting..')
wp_exports = glob(wp_exports + '/*.xml')
for wpe in wp_exports:
    data = parse_wp_xml(wpe)
    write_hugo(data, target_format)

print('done')
