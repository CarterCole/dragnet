#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Implementation of the blockifier interface and some classes
to manipulate blocks

blockifier interface is any object that implements blockify(html) and
returns a list of Block instances
"""

import re
from lxml import etree
import numpy as np
from itertools import chain
import scipy.weave


class Block(object):
    def __init__(self, text, link_density, text_density, anchors, link_tokens, css):
        self.text = text
        self.link_density = link_density
        self.text_density = text_density
        self.anchors = anchors
        self.link_tokens = link_tokens  # a hook for testing
        self.css = css

class BlockifyError(Exception):
    """Raised when there is a fatal problem in blockify
    (if lxml fails to parse the document)
    """
    pass


class PartialBlock(object):
    """As we create blocks by recursing through subtrees
    in Blockifier, we need to maintain some state
    of the incomplete blocks.

    This class maintains that state, as well as provides methods
    to modify it."""

    css_attrib = ['id', 'class']

    def __init__(self):
        self.reinit()
        self.reinit_css(init_tree=True)

    def reinit(self):
        self.text = []
        self.link_tokens = []
        self.anchors = []

    def reinit_css(self, init_tree=False):
        # we want to keep track of the id and class CSS attributes.
        # we will accumulate a few sources of them
        # (1) the CSS attributes for the current tag and all tags in trees containing
        #     the current one
        # (2) the CSS attributes for all tags inside this block

        # css_tree will hold the attributes for all trees containing this tag
        # css will hold the accumulated attributes for this block,
        #   and will be initialized with the tree

        if init_tree:
            # the initial init
            self.css_tree = {}
            self.css = {}
            for k in PartialBlock.css_attrib:
                self.css_tree[k] = []
                self.css[k] = []
        else:
            # we are re-initializing after creating a block
            # css_tree is unchanged and css is set to css_tree
            self.css = {}
            for k in PartialBlock.css_attrib:
                self.css[k] = []



    def add_block_to_results(self, results):
        """Create a block from the current partial block
        and append it to results.  Reset the partial block"""
        # compute block and link tokens!
        block_tokens = PartialBlock.tokens_from_text(self.text)
        if len(block_tokens) > 0:
            # only process blocks with something other then white space
            block_text = ' '.join(block_tokens)
            link_text = ' '.join(PartialBlock.tokens_from_text(self.link_tokens))

            # compute link/text density
            link_d = PartialBlock.link_density(block_text, link_text)
            text_d = PartialBlock.text_density(block_text)

            # get the id, class attributes
            css = {}
            for k in PartialBlock.css_attrib:
                css[k] = ' '.join(PartialBlock.tokens_from_text(self.css[k])).lower()

            results.append(Block(block_text, link_d, text_d, self.anchors, self.link_tokens, css))
        self.reinit()
        self.reinit_css()

    def add_text(self, ele, text_or_tail):
        """Add the text/tail from the element
        element is an etree element
        text_or_tail is 'text' or 'tail'"""
        # we need to wrap it in a try/catch block
        # if there is an invalid unicode byte in the HTML,
        # lxml raises an error when we try to get the .text or .tail
        try:
            text = getattr(ele, text_or_tail)
            if text is not None:
                self.text.append(text)
        except UnicodeDecodeError:
            pass

    def add_anchor(self, tree):
        """Add the anchor tag to the block.
        tree = the etree a element"""
        self.anchors.append(tree)
        # need all the text from the subtree
        anchor_text_list = PartialBlock._text_from_subtree(tree, tags_exclude=Blockifier.blacklist, tail=False)
        self.text.extend(anchor_text_list)
        try:
            self.text.append(tree.tail or '')
        except UnicodeDecodeError:
            pass
        self.link_tokens.extend(PartialBlock.tokens_from_text(anchor_text_list))


    @staticmethod
    def _text_from_subtree(tree, tags_exclude=set(), tail=True):
        """Get all the text
        from the subtree, excluding tags_exclude
        If tail=False, then don't append the tail for this top level element"""
        try:
            text = [tree.text or '']
        except UnicodeDecodeError:
            text = []
        for child in tree.iterchildren():
            if child.tag not in tags_exclude:
                text.extend(PartialBlock._text_from_subtree(child, tags_exclude=tags_exclude))
            else:
                # get the tail
                try:
                    text.append(child.tail or '')
                except UnicodeDecodeError:
                    pass
        if tail:
            try:
                text.append(tree.tail or '')
            except UnicodeDecodeError:
                pass
        return text


    @staticmethod
    def tokens_from_text(text):
        """given a of text (as built in self.text for example)
        return a list of tokens.

        according to 
        http://stackoverflow.com/questions/952914/making-a-flat-list-out-of-list-of-lists-in-python
        chain is the fastest way to combine the list of lists"""
        return list(chain.from_iterable([re.split('\s+', ele.strip()) for ele in text if ele.strip() != '']))

    @staticmethod
    def link_density(block_text, link_text):
        '''
        Assuming both input texts are stripped of excess whitespace, return the 
        link density of this block
        '''
        # NOTE: in the case where link_text == '', this re.split
        # returns [''], which incorrectly
        # has 1 token by it's length instead of 0
        # however, fixing this bug decreases model performance by about 1%,
        # so we keep it
        anchor_tokens = re.split(r'\W+', link_text)
        block_tokens  = re.split(r'\W+', block_text)
        return float(len(anchor_tokens)) / len(block_tokens)


    @staticmethod
    def text_density(block_text):
        '''
        Assuming the text has been stripped of excess whitespace, return text
        density of this block
        '''
        import math
        lines  = math.ceil(len(block_text) / 80.0)

        if int(lines) == 1:
            tokens = re.split(r'\W+', block_text)
            return float(len(tokens))
        else:
            # need the number of tokens excluding the last partial line
            tokens = re.split(r'\W+', block_text[:(int(lines - 1) * 80)])
            return len(tokens) / (lines - 1.0)


    @staticmethod
    def recurse(subtree, partial_block, results):
        # both partial_block and results are modified
#        print("%s %s" % ( subtree.tag, partial_block.css_tree))

        # for CSS, we want to output all CSS tags for all levels in subtree
        # we will add them on entry, and pop them on exit
        partial_block.update_css(subtree, True)

        for child in subtree.iterchildren():

            if child.tag in Blockifier.blacklist:
                # in this case, skip the entire tag,
                # but it might have some tail text we need
                partial_block.add_text(child, 'tail')

            elif child.tag in Blockifier.blocks:
                # this is the start of a new block
                # add the existing block to the list,
                # start the new block and recurse
#                print("sdfsadf %s %s " % (child.tag, partial_block.css_tree))
                partial_block.add_block_to_results(results)
                partial_block.add_text(child, 'text')
                partial_block.update_css(child, False)
                PartialBlock.recurse(child, partial_block, results)
                partial_block.add_text(child, 'tail')

            elif child.tag == 'a':
                # an anchor tag
                partial_block.add_anchor(child)
                partial_block.update_css(child, False)

            else:
                # a standard tag.
                # we need to get it's text and then recurse over the subtree
                partial_block.add_text(child, 'text')
                partial_block.update_css(child, False)
                PartialBlock.recurse(child, partial_block, results)
                partial_block.add_text(child, 'tail')

        partial_block.pop_css_tree()

    def update_css(self, child, tree):
        """Add the child's tag to the id, class lists"""
        if tree:
            css_to_update = self.css_tree
        else:
            css_to_update = self.css

        for k in PartialBlock.css_attrib:
            try:
                css_to_update[k].append(child.attrib[k])
            except KeyError:
                css_to_update[k].append('')


    def pop_css_tree(self):
        """pop the last entry off the css lists"""
        for k in PartialBlock.css_attrib:
            self.css_tree[k].pop()



class Blockifier(object):
    """A blockifier for web-page de-chroming that loosely follows the approach in
        Kohlschütter et al.:
        http://www.l3s.de/~kohlschuetter/publications/wsdm187-kohlschuetter.pdf

      Implements the blockify interface
    """

    # All of these tags will be /completely/ ignored
    blacklist = set([
        etree.Comment, 'applet', 'area', 'base', 'basefont', 'bdo', 'button', 
        'caption', 'fieldset', 'fram', 'frameset', 
        'iframe', 'img', 'input', 'legend', 'link', 'menu', 'meta', 
        'noframes', 'noscript', 'object', 'optgroup', 'option', 'param', 
        'script', 'select', 'style', 'textarea', 'var', 'xmp',
        'like', 'like-box', 'plusone'
    ])
    
    # Only these should be considered as housing blocks of text
    blocks = set([
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'table', 'map'
    ])
    

    @staticmethod
    def blocks_from_tree(tree):
        results = []
        partial_block = PartialBlock()

        PartialBlock.recurse(tree, partial_block, results)

        # make the final block
        partial_block.add_block_to_results(results)
        return results
    

    @staticmethod
    def blockify(s):
        '''
        Take a string of HTML and return a series of blocks
        '''
        # First, we need to parse the thing
        try:
            html = etree.fromstring(s, etree.HTMLParser(recover=True))
        except:
            raise BlockifyError
        if html is None:
            # lxml sometimes doesn't raise an error but returns None
            raise BlockifyError

        blocks = Blockifier.blocks_from_tree(html)
        # only return blocks with some text content
        return [ele for ele in blocks if re.sub('[\W_]', '', ele.text).strip() != '']
