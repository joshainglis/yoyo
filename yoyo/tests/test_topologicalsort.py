import itertools

import pytest

from yoyo import topologicalsort


class TestTopologicalSort(object):
    def check(self, nodes, edges, expected):
        deps = {}
        edges = edges.split() if edges else []
        for a, b in edges:
            deps.setdefault(a, set()).add(b)
        output = list(topologicalsort.topological_sort(nodes, deps))
        for a, b in edges:
            try:
                assert output.index(a) > output.index(b)
            except ValueError:
                pass
        assert output == list(expected)

    def test_it_keeps_stable_order(self):
        for s in map(str, itertools.permutations("ABCD")):
            self.check(s, "", s)

    def test_it_sorts_topologically(self):

        # Single group at start
        self.check("ABCD", "BA", "ABCD")
        self.check("BACD", "BA", "ABCD")

        # Single group in middle start
        self.check("CABD", "BA", "CABD")
        self.check("CBAD", "BA", "CABD")

        # Extended group
        self.check("ABCD", "BA DA", "ABCD")
        self.check("DBCA", "BA DA", "CADB")

        # Non-connected groups
        self.check("ABCDEF", "BC DE", "ACBEDF")
        self.check("ADEBCF", "BC DE", "AEDCBF")
        self.check("ADEFBC", "BC DE", "AEDFCB")
        self.check("DBAFEC", "BC DE", "AFEDCB")

    def test_it_discards_missing_dependencies(self):
        self.check("ABCD", "CX XY", "ABCD")

    def test_it_catches_cycles(self):
        with pytest.raises(topologicalsort.CycleError):
            self.check("ABCD", "AA", "")
        with pytest.raises(topologicalsort.CycleError):
            self.check("ABCD", "AB BA", "")
        with pytest.raises(topologicalsort.CycleError):
            self.check("ABCD", "AB BC CB", "")
        with pytest.raises(topologicalsort.CycleError):
            self.check("ABCD", "AB BC CA", "")

    def test_it_handles_multiple_edges_to_the_same_node(self):
        self.check("ABCD", "BA CA DA", "ABCD")
        self.check("DCBA", "BA CA DA", "ADCB")

    def test_it_handles_multiple_edges_to_the_same_node2(self):
        #      A --> B
        #      |     ^
        #      v     |
        #      C --- +
        for input_order in itertools.permutations("ABC"):
            self.check(input_order, "BA CA BC", "ACB")

    def test_it_doesnt_modify_order_unnecessarily(self):
        """
        Test for issue raised in

        https://lists.sr.ht/~olly/yoyo/%3C09c43045fdf14024a0f2e905408ea41f%40atos.net%3E
        """
        self.check("ABC", "CA", "ABC")
