"""Bounded, canonical Desktop Menu categories, shared across the trust boundary.

Registry: https://specifications.freedesktop.org/menu/latest/category-registry.html
and additional-category-registry.html (reviewed 2026-10-31). No runtime downloads.
Related main categories are used to filter unrelated additions or supply a main
category when only a useful additional classification was provided.
"""
from __future__ import annotations

import re

MAX_CATEGORY_TEXT = 1024
MAX_CATEGORIES = 32
MAIN = frozenset('AudioVideo Audio Video Development Education HealthFitness Game Graphics Network Office Science Settings System Utility'.split())
_GROUPS = (
    (('Development',), 'Building Debugger IDE GUIDesigner Profiling RevisionControl Translation'),
    (('Office',), 'Calendar ContactManagement Chart Finance FlowChart PDA Presentation Spreadsheet WordProcessor'),
    (('Office', 'Development', 'AudioVideo'), 'Database'),
    (('Office', 'Utility'), 'Dictionary'),
    (('Office', 'Network'), 'Email'),
    (('Office', 'Development'), 'ProjectManagement'),
    (('Graphics',), '2DGraphics VectorGraphics RasterGraphics 3DGraphics Scanning OCR'),
    (('Graphics', 'Office'), 'Photography Publishing Viewer'),
    (('Utility',), 'TextTools TelephonyTools Archiving Compression Calculator Clock TextEditor'),
    (('Settings',), 'DesktopSettings HardwareSettings Printing PackageManager'),
    (('Network',), 'Dialup InstantMessaging Chat IRCClient Feed FileTransfer News P2P RemoteAccess Telephony VideoConference WebBrowser'),
    (('Network', 'AudioVideo'), 'HamRadio'),
    (('Network', 'Development'), 'WebDevelopment'),
    (('AudioVideo',), 'Midi Mixer Sequencer Tuner TV AudioVideoEditing Player Recorder DiscBurning'),
    (('Game',), 'ActionGame AdventureGame ArcadeGame BoardGame BlocksGame CardGame KidsGame LogicGame RolePlaying Shooter Simulation SportsGame StrategyGame LauncherStore GameTool'),
    (('HealthFitness',), 'Exercise Medication Mindfulness Nutrition CareProvider Sleep'),
    (('Education', 'Science'), 'Art Construction Languages ArtificialIntelligence Astronomy Biology Chemistry ComputerScience DataVisualization Economy Electricity Geography Geology Geoscience History Humanities ImageProcessing Literature Math NumericalAnalysis MedicalSoftware Physics Robotics Sports ParallelComputing'),
    (('AudioVideo', 'Education'), 'Music'),
    (('Education', 'Science', 'Utility'), 'Maps Spirituality'),
    (('System', 'Game'), 'Emulator'),
    (('Utility', 'System'), 'FileTools'),
    (('System',), 'FileManager TerminalEmulator Filesystem'),
    (('System', 'Network'), 'Monitor'),
    (('Settings', 'System'), 'Security'),
    (('Settings', 'Utility'), 'Accessibility'),
    ((), 'Amusement Electronics Engineering Documentation Adult Core KDE COSMIC GNOME LXQt XFCE DDE GTK Qt Motif Java'),
)
RELATED = {name: parents for parents, names in _GROUPS for name in names.split()}
# Reserved/custom categories are not imported. ConsoleOnly is inconsistent with
# the fixed Terminal=false launcher and is deliberately not carried over.


def normalize_categories(value: str) -> tuple[str, ...]:
    """Optional original field: malformed => neutral fallback, unknown => omit."""
    if (not isinstance(value, str) or not value or len(value) > MAX_CATEGORY_TEXT
            or not re.fullmatch(r'(?:[A-Za-z0-9][A-Za-z0-9-]*;)+', value)):
        return ('Utility',)
    tokens = list(dict.fromkeys(value[:-1].split(';')))
    if value.count(';') > MAX_CATEGORIES:
        return ('Utility',)
    tokens = [name for name in tokens if name in MAIN or name in RELATED]
    main = set(tokens) & MAIN
    if main & {'Audio', 'Video'} and 'AudioVideo' not in main:
        tokens.append('AudioVideo')
        main.add('AudioVideo')
    if not main:
        inferred = next((RELATED[name][0] for name in tokens if RELATED.get(name)), 'Utility')
        main.add(inferred)
        tokens.append(inferred)
    result = tuple(name for name in tokens if name in main or (name in RELATED and
                   (not RELATED[name] or main.intersection(RELATED[name]))))
    # Inference can add one category; keep the protocol's fixed bound.
    return result if len(result) <= MAX_CATEGORIES else ('Utility',)


def validate_categories(value: object) -> tuple[str, ...]:
    """Administrative protocol: refuse noncanonical input; never fix it silently."""
    if (not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_CATEGORIES
            or any(not isinstance(name, str) or not name or len(name) > 64 for name in value)):
        raise ValueError('Lista de categorias inválida.')
    result = tuple(value)
    if normalize_categories(';'.join(result) + ';') != result:
        raise ValueError('Categorias desconhecidas, malformadas ou não canônicas.')
    return result


def categories_field(value: object) -> str:
    return ';'.join(validate_categories(value)) + ';'
