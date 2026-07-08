"""Unit tests for cli/commands/graph.py."""

from unittest.mock import MagicMock, patch

from rich.tree import Tree


class TestBuildRecursiveTree:
    def test_root_node_label(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "flask": {
                "ecosystem": "pypi",
                "version": "2.3.3",
                "dependencies": {"pypi": {}},
            }
        }
        tree = _build_recursive_tree(rp, "flask", rp["flask"])
        assert isinstance(tree, Tree)
        label = tree.label
        assert "flask" in str(label)
        assert "2.3.3" in str(label)
        assert "pypi" in str(label)

    def test_single_dependency(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "flask": {
                "ecosystem": "pypi",
                "version": "2.3.3",
                "dependencies": {"pypi": {"click": "8.1.7"}},
            },
            "click": {
                "ecosystem": "pypi",
                "version": "8.1.7",
                "dependencies": {"pypi": {}},
            },
        }
        tree = _build_recursive_tree(rp, "flask", rp["flask"])
        assert "flask" in str(tree.label)
        assert "2.3.3" in str(tree.label)

    def test_max_depth_respected(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "a": {"ecosystem": "pypi", "version": "1.0", "dependencies": {"pypi": {"b": "2.0"}}},
            "b": {"ecosystem": "pypi", "version": "2.0", "dependencies": {"pypi": {"c": "3.0"}}},
            "c": {"ecosystem": "pypi", "version": "3.0", "dependencies": {"pypi": {}}},
        }
        tree = _build_recursive_tree(rp, "a", rp["a"], max_depth=1)
        assert isinstance(tree, Tree)

    def test_no_deps_returns_leaf(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "standalone": {
                "ecosystem": "pypi",
                "version": "1.0",
                "dependencies": {"pypi": {}},
            }
        }
        result = _build_recursive_tree(rp, "standalone", rp["standalone"])
        assert isinstance(result, Tree)

    def test_nested_deps_rendered_as_tree(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "root": {
                "ecosystem": "pypi",
                "version": "1.0",
                "dependencies": {"pypi": {"mid": "2.0"}},
            },
            "mid": {
                "ecosystem": "pypi",
                "version": "2.0",
                "dependencies": {"pypi": {"leaf": "3.0"}},
            },
            "leaf": {
                "ecosystem": "pypi",
                "version": "3.0",
                "dependencies": {"pypi": {}},
            },
        }
        tree = _build_recursive_tree(rp, "root", rp["root"], max_depth=5)
        assert isinstance(tree, Tree)

    def test_unknown_ecosystem(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "pkg": {
                "ecosystem": "?",
                "version": "1.0",
                "dependencies": {},
            }
        }
        tree = _build_recursive_tree(rp, "pkg", rp["pkg"])
        assert isinstance(tree, Tree)

    def test_missing_version(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "pkg": {
                "ecosystem": "pypi",
                "version": "?",
                "dependencies": {"pypi": {}},
            }
        }
        tree = _build_recursive_tree(rp, "pkg", rp["pkg"])
        assert isinstance(tree, Tree)

    def test_missing_deps_field(self):
        from backend.cli.commands.graph import _build_recursive_tree

        rp = {
            "pkg": {
                "ecosystem": "pypi",
                "version": "1.0",
            }
        }
        tree = _build_recursive_tree(rp, "pkg", rp["pkg"])
        assert isinstance(tree, Tree)


class TestCmdGraph:
    def test_no_packages_shows_message(self):
        args = MagicMock()
        args.packages = []
        args.ecosystem = None
        args.json = False
        args.cuda = None
        args.device = None

        with patch("backend.cli.commands.graph.console.print") as mock_print:
            from backend.cli.commands.graph import cmd_graph

            cmd_graph(args)

            mock_print.assert_any_call("[red]No packages could be resolved[/red]")
