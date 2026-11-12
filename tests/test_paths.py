import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"payload/mods/wsl-clipboard"))
import open_path


class PathOpeningTests(unittest.TestCase):
    def test_wsl_path_and_line_reference(self):
        self.assertEqual(open_path.windows_path('/home/demo/검수 자료.zip','Ubuntu-24.04'),
                         '\\\\wsl.localhost\\Ubuntu-24.04\\home\\demo\\검수 자료.zip')

    def test_mounted_drive_and_windows_path(self):
        self.assertEqual(open_path.windows_path('/mnt/c/Users/A User/a.zip','Ubuntu'),
                         'C:\\Users\\A User\\a.zip')
        self.assertEqual(open_path.windows_path(r'C:\Users\A User\a.zip','Ubuntu'),
                         r'C:\Users\A User\a.zip')

    def test_relative_and_home_paths(self):
        self.assertEqual(open_path.windows_path('~/file.zip','Ubuntu','/home/demo/project'),
                         '\\\\wsl.localhost\\Ubuntu\\home\\demo\\file.zip')
        self.assertEqual(open_path.windows_path('src/main.py','Ubuntu','/home/demo/project'),
                         '\\\\wsl.localhost\\Ubuntu\\home\\demo\\project\\src\\main.py')

    def test_file_url_and_surrounding_prose(self):
        value=open_path.selected_path('검수 ZIP (/home/demo/최종음성.zip)에서:')
        self.assertEqual(value,'/home/demo/최종음성.zip')
        self.assertEqual(open_path.windows_path('file:///C:/Users/A%20User/a.zip',None),
                         'C:\\Users\\A User\\a.zip')

    def test_selection_with_partial_markdown_closing_bracket(self):
        path = '/home/demo/.local/share/evento-notice-preview/personal-main-mobile.png'
        expected = open_path.windows_path(path, 'Ubuntu-24.04')
        for selected in [path + ')', path + ').', '(' + path + ')', '[preview](' + path + ')']:
            self.assertEqual(open_path.resolve_existing_path(selected, 'Ubuntu-24.04', exists=lambda p: p == expected), expected)

    def test_soft_wrapped_terminal_selection(self):
        expected = open_path.windows_path('/home/demo/한글 자료/image.png', 'Ubuntu-24.04')
        selected = '/home/demo/한글 자료/\r\nimage.png)'
        self.assertEqual(open_path.resolve_existing_path(selected, 'Ubuntu-24.04', exists=lambda p: p == expected), expected)

    def test_exact_filename_punctuation_is_preserved(self):
        for path in ['/home/demo/report).png', '/home/demo/report)', '/home/demo/report.', '/home/demo/report(test)']:
            exact = open_path.windows_path(path, 'Ubuntu-24.04')
            self.assertEqual(open_path.resolve_existing_path(path, 'Ubuntu-24.04', exists=lambda p: p == exact), exact)

    def test_padded_markdown_with_parentheses_in_filename(self):
        self.assertEqual(open_path.selected_path('  미리보기 (/home/demo/report(test).png)입니다'), '/home/demo/report(test).png')

    def test_line_column_reference(self):
        expected = open_path.windows_path('/home/demo/test.py', 'Ubuntu-24.04')
        self.assertEqual(open_path.resolve_existing_path('/home/demo/test.py:12:3', 'Ubuntu-24.04', exists=lambda p: p == expected), expected)

    def test_unsupported_context_is_not_guessed(self):
        with self.assertRaises(ValueError):
            open_path.windows_path('/home/demo/file.zip',None)
        with self.assertRaises(ValueError):
            open_path.windows_path('',None)


if __name__=='__main__':unittest.main()
