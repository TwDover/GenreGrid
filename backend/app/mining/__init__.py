# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Corpus-mining pipeline.

Extracts musical statistics (key, chord-progression n-grams, melodic phrase and
rhythm distributions) from a directory of real MIDI files, so the procedural
generators can be biased by what real songs of a genre actually do instead of
hand-written templates. See ``corpus.mine_directory`` and ``scripts/mine_corpus.py``.
"""
