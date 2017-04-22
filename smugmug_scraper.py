# -*- coding: utf-8 -*-
# @Author: Evan Laske
# @Date:   2017-04-21 18:26:45
# @Last Modified by:   Evan Laske
# @Last Modified time: 2017-04-21 22:50:29

import urllib
import json
import re
import os
import string
import logging

def get_gallery_config_from_html(html):
    """
    Finds the gallery configuration from the initial html page.

    Params:
        html (str) - initial loaded HTML containing galleryConfig

    Returns: 
        dict of gallery configuration.
    """
    # trust but verify
    if not type(html) is str:
        raise TypeError("Type of html is not a string.")

    # Generated with https://regex101.com/r/GFFZct/1
    gallery_config = re.compile(r'.*?galleryConfig\s*=\s*({.*?})\s*;')

    # Go through all the lines
    for line in html.split('\n'):
        # If there was a match
        if "galleryConfig" in line:
            json_text = gallery_config.search(line)
            logging.debug("`{}` found in `{}`".format(json_text, line))
            # Take the first matched group in the MatchObject
            parsed = json.loads(json_text.group(1))
            logging.info("Parsed JSON string with galleryConfig: \n{}".format(json.dumps(parsed, indent=4, sort_keys=True)))
            return parsed

    raise ValueError("HTML did not include any gallery configuration.")


def request_album_data(gallery_config):
    """
    Gets album metadata including Title, Pagination, etc parsed from JSON to dict.

    Params:
        gallery_config (dict) - gallery configuration dictionary

    Optional:
        sm_api_base (str) - SmugMug API base URL

    Returns:
        album_data (dict) - 
    """
    url = build_request_url(gallery_config)

    logging.info("Requesting Album Data from: {}".format(url))

    # Get the JSON data:
    json_text = urllib.urlopen(url).read()
    logging.debug("Received Album Data Response: {}".format(json_text))

    parsed = json.loads(json_text)
    logging.info("Received Album Data: \n{}".format(json.dumps(parsed, indent=4, sort_keys=True)))

    return parsed


def build_request_url(gallery_config, size=0, sm_api_base="/services/api/json/1.4.0/", method='rpc.gallery.getalbum'):
    """
    Builds a URL to request data from the API
    """
    # verify that the parameters we need are in here
    if not type(gallery_config) is dict:
        raise TypeError("Type of gallery_config is not a dictionary.")
    if not ("breadcrumbs" in gallery_config and "galleryRequestData" in gallery_config):
        raise ValueError("gallery_config missing fields")

    # Find the first non-blank url and use that to start
    base_url = [x["url"] for x in gallery_config["breadcrumbs"] if x["url"]][0]
    # Gather all the parameters
    params = gallery_config["galleryRequestData"]
    params["method"] = method           # Use this method
    params["returnModelList"] = True    # Enable the PageSize variable
    params["PageSize"] = size           # Make this lightweight - don't grab image info.
    query_string = urllib.urlencode(params)
    # Generate the full URL
    url = base_url + sm_api_base + "?" + query_string;

    return url


def request_image_data(gallery_config, album_data):
    """
    Returns a list of images data from the album.

    Params: 
        gallery_config (dict) - gallery configuration dictionary
        album_data (dict) - album and pagination information

    Returns:
        images (list(dict)) - list of image data
    """
    if not type(album_data) is dict:
        raise TypeError("Type of album_data is not a dictionary.")
    if not ("Pagination" in album_data):
        raise ValueError("album_data missing fields")

    # Build the URL with the size of TotalItems
    url = build_request_url(gallery_config, size=album_data["Pagination"]["TotalItems"])

    logging.info("Requesting All Image Data from: {}".format(url))

    # Get the JSON data:
    json_text = urllib.urlopen(url).read()
    logging.debug("Received Image Data Response: {}".format(json_text))

    parsed = json.loads(json_text)
    logging.info("Received Image Data for {} images.".format(len(parsed["Images"])))

    return parsed["Images"]


def get_image_url(image_data, sizes=None):
    """
    Generates the URL of an image from the image data.

    Params:
        image_data (dict) - a single image data structure
        sizes (list(str) / str) - None / Size / List of sizes

    Returns:
        URL(s) in various form:
            size = None: URL as a generic string
    """
    if not type(image_data) is dict:
        raise TypeError("Type of image_data is not a dictionary.")
    if not ("BaseUrl" in image_data and "ImageKey" in image_data and "URLFilename" in image_data):
        raise ValueError("iamge_data missing fields")

    # Generate a list of sizes from sizes
    # If none, the list will be all of them:
    if not sizes:
        sizes = image_data["Sizes"].keys()
    # If there's one to use
    elif type(sizes) is str:
        if sizes in image_data["Sizes"]:
            sizes = [sizes]
        else:
            raise ValueError("Size {} not in {}".format(sizes, image_data["Sizes"]))
    elif type(sizes) is list:
        sizes = [s for s in sizes if s in image_data["Sizes"]]
    else:
        raise TypeError("size wasn't an expected type")

    logging.info("Generating URLs for sizes {}".format(sizes))

    # Generate all the URLs from the list of sizes:
    urls = []
    for s in sizes:
        urls.append("{BaseUrl}i-{ImageKey}/1/{size}/{URLFilename}-{size}.{ext}".format(
                            BaseUrl=image_data["BaseUrl"],
                            ImageKey=image_data["ImageKey"],
                            size=s,
                            URLFilename=image_data["URLFilename"],
                            ext=image_data["Sizes"][s]["ext"]
                        )
                    )
    return urls[0] if len(urls) == 1 else urls


def get_valid_image_sizes(image_data):
    """
    Returns a list of strings representing the valid sizes for this image.

    Params:
        image_data (dict) - a single image data structure

    Returns:
        sizes (list(str)) - list of valid image size strings.
    """
    raise NotImplementedError()


def get_album_name(album_data):
    """
    Gets the album name from the album_data sanitized for paths.

    Params:
        album_data (dict) - album and pagination information
    """
    if not type(album_data) is dict:
        raise TypeError("Type of album_data is not a dictionary.")

    # Get the title from the album
    title = album_data["Albums"][0]["Title"]
    print(title)

    # Reserved characters in a folder/file name... Python 2 sucks:
    to_remove = r'[\/\*\?:"<>]+'
    title = ''.join(re.split(to_remove, title))

    print(title)
    return title


def download_album(url, output_dir, sizes):
    """
    Downloads all of the images in the given sizes from a url to a directory.

    Params:
        url (str) - url to download from
        output_dir (str) - directory to download album to
        sizes (list(str)) - list of sizes to download
    """
    # Get the initial HTML from the URL
    html = urllib.urlopen(url).read()
    logging.debug("HTML: {}".format(html))
    # Parse the HTML
    gallery_config = get_gallery_config_from_html(html)
    # Request album information
    album_data = request_album_data(gallery_config)
    # Get all the image info
    image_data = request_image_data(gallery_config, album_data)
    print("Found {} images.".format(len(image_data)))

    # Get the directory to save the file:
    output_dir = os.path.join(output_dir, get_album_name(album_data))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    print("Outputting to {}".format(output_dir))

    # Download all of the images
    for i in image_data:
        # Get the image urls
        image_urls = get_image_url(i, sizes)
        if type(image_urls) is str:
            download_file(image_urls, output_dir)
        elif type(image_urls) is list:
            for u in image_urls:
                download_file(u, output_dir)


def download_file(url, output_dir):
    print("Downloading {}...".format(os.path.basename(url)))
    urllib.urlretrieve(url, os.path.join(output_dir, os.path.basename(url)))


def main(urls, output_dir, sizes):
    for url in urls:
        print("Processing {}".format(url))
        download_album(url, output_dir, sizes)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output_dir', dest='output_dir', help="Output directory to place pictures.")
    parser.add_argument('-s', '--sizes', nargs="*", help="Specific sizes to download.")
    parser.add_argument('--logfile', dest='logfile', default='', help='Specify a log file to log info to.')
    parser.add_argument('--loglevel', dest='loglevel', default='', help='Specify a logging level to output.')
    parser.add_argument('url', type=str, nargs='+', help="Album URL(s).")
    args = parser.parse_args()

    # Logging configuration args
    logConfigArgs = dict()
    # If the log level was specified 
    if args.loglevel:
        # Convert it to something usable
        numeric_level = getattr(logging, args.loglevel.upper(), None)
        # Double-check it's a valid logging level
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % args.loglevel)
        logConfigArgs['level'] = numeric_level
    # If there was any of the logging files specified...
    if args.logfile:
        logConfigArgs['filename'] = args.logfile
        # This will make the log file be overwritten each time.
        logConfigArgs['filemode'] = 'w'

    # If any of the logging arguments are specified, configure logging
    if args.logfile or args.loglevel:
        logging.basicConfig(**logConfigArgs)

    # Normalize path to not be shitty
    output_dir = os.path.normpath(args.output_dir)
    print("Downloading to {}".format(output_dir))

    # Do work!
    main(args.url, output_dir, args.sizes)