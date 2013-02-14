
import unittest
from dragnet import blocks
from html_for_testing import big_html_doc

class Testencoding(unittest.TestCase):
    def test_guess_encoding(self):
        s = """<?xml version="1.0" encoding="ISO-8859-1"?>
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
          "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

          <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="fr" lang="fr">
          """
        self.assertEqual(blocks.guess_encoding(s), 'ISO-8859-1')

        s = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
          "http://www.w3.org/TR/html4/strict.dtd">
                 
          <head>
          <meta http-equiv="content-type" content="text/html; charset=GB2312">
          </head>"""
        self.assertEqual(blocks.guess_encoding(s), 'GB2312')

        s = """<html>sadfsa</html>"""
        self.assertEqual(blocks.guess_encoding(s, 'asciI'), 'asciI')




class Test_text_subtree(unittest.TestCase):
    def test_text_from_subtree(self):
        from lxml import etree
        s = """<a href=".">WILL <img src="."> THIS PASS <b>THE TEST</b> ??</a>"""
        tree = etree.fromstring(s, etree.HTMLParser(recover=True))
        text_list = blocks.text_from_subtree(tree, tags_exclude=blocks.Blockifier.blacklist)
        text_str = ' '.join([ele.strip() for ele in text_list if ele.strip() != ''])
        self.assertEqual(text_str,
            'WILL THIS PASS THE TEST ??')


class Test_TagCountPB(unittest.TestCase):

    def check_tagcount(self, expected, predicted):
        self.assertEqual(predicted['tagcount'],
                        expected[0])
        self.assertEqual(predicted['tagcount_since_last_block'],
                expected[1])

    def test_simple(self):
        s = """<html><body><div>some text <i>in italic</i> and something else
                    <script> <div>skip this</div> </script>
                    <b>bold stuff</b> after the script
               </div></body></html>"""
        blks = blocks.TagCountBlockifier.blockify(s)
        self.check_tagcount((3, 2), blks[0].features)
        self.assertTrue(len(blks) == 1)
        
    def test_big_html(self):
        blks = blocks.TagCountBlockifier.blockify(big_html_doc)

        actual_features = [
            (1, 2),
            (2, 0),
            (2, 0),
            (2, 0),  # blockquote
            (1, 2),
            (1, 0),
            (1, 0),
            (1, 2), # first comment
            (2, 0),
            (1, 1),
            (3, 0)  # NOTE: this is a bug here.  It's due
                    # to the _tc-1 assumption in the feature extractor
                    # that fails for the last block. (we don't call
                    # tag_tagcount again before appending the block)
            ]

        for a, b in zip(actual_features, blks):
            self.check_tagcount(a, b.features)


if __name__ == "__main__":
    unittest.main()

