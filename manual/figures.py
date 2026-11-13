#!/usr/bin/env python3
"""The manual's pictures with their numbered callouts: the station's flight display and map (canvases saved from the
running page), the head-up display and the belly camera's picture (FlightGear screenshots), and the page's layout.
The pictures are in fig/raw/; the numbers here are explained in the manual's text."""
import os

import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt     # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, 'fig')
plt.rcParams.update({'font.family': 'serif', 'font.size': 8})


def called(name, marks, width=6.0, light=True):
    """a picture with numbered marks: (number, x, y of what is meant, x, y of the number), in the picture's pixels"""
    im = Image.open(os.path.join(F, 'raw', name + '.png')).convert('RGB')
    fig = plt.figure(figsize=(width, width * im.height / im.width))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(im)
    ax.axis('off')
    for n, x, y, tx, ty in marks:
        ax.annotate(str(n), (x, y), (tx, ty), ha='center', va='center', fontsize=7.5, fontweight='bold', color='black',
                    bbox=dict(boxstyle='circle,pad=0.25', fc='#ffe14d', ec='black', lw=0.6),
                    arrowprops=dict(arrowstyle='-', color='#ffe14d', lw=0.9, shrinkA=0, shrinkB=1))
    fig.savefig(os.path.join(F, name + '.pdf'), dpi=220)
    plt.close(fig)


def layout():
    """the page, as areas: where to look for what"""
    fig, ax = plt.subplots(figsize=(6.4, 4.1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis('off')
    boxes = [(1, 0, 57, 100, 7, 'Doing, Next   |   Altitude   |   Speed   |   Link', '#dbe7f5'),
             (2, 0, 52.5, 100, 4, 'Alerts: one list, the worst on top', '#f6dcd9'),
             (3, 0, 14, 66, 38, 'Map', '#eeeeee'),
             (4, 0, 7.5, 66, 6, 'Height profile', '#eeeeee'),
             (5, 0, 0, 66, 7, 'Confirm bar: what is about to be sent.   Send   Cancel', '#fdf2c4'),
             (6, 67, 37, 33, 15, 'Flight display', '#dbe7f5'),
             (7, 67, 31, 33, 5.5, 'Aircraft; Engine and fuel; Navigators', '#eeeeee'),
             (8, 67, 25, 33, 5.5, 'Control; Station; Messages', '#eeeeee'),
             (9, 67, 19, 33, 5.5, 'By hand', '#eeeeee'),
             (10, 67, 13, 33, 5.5, 'Commands; Camera', '#e3f1e0'),
             (11, 67, 7, 33, 5.5, 'Plan editor (when open)', '#eeeeee'),
             (12, 67, 0, 33, 6.5, 'Sent; From the aircraft', '#eeeeee')]
    for n, x, y, w, h, text, col in boxes:
        ax.add_patch(Rectangle((x, y), w, h, fc=col, ec='0.3', lw=0.6))
        ax.text(x + 3.2, y + h - 2.2, str(n), ha='center', va='center', fontsize=7.5, fontweight='bold', bbox=dict(boxstyle='circle,pad=0.25', fc='#ffe14d', ec='black', lw=0.6))
        if w > 40 or h > 10:
            ax.text(x + w / 2 + 1.5, y + h / 2, text, ha='center', va='center', fontsize=7.5)
        else:
            ax.text(x + 6.5, y + h / 2, text, ha='left', va='center', fontsize=6.4)
    fig.savefig(os.path.join(F, 'layout.pdf'), bbox_inches='tight', pad_inches=0.02)
    plt.close(fig)


if __name__ == '__main__':
    called('pfd-turn', [(1, 520, 26, 610, 70), (2, 30, 38, 30, 100), (3, 62, 258, 150, 215), (4, 116, 100, 190, 60), (5, 116, 440, 190, 480),
                        (6, 322, 82, 322, 150), (7, 400, 82, 470, 130), (8, 322, 268, 322, 340), (9, 380, 258, 440, 215), (10, 700, 38, 745, 100),
                        (11, 590, 258, 470, 300), (12, 775, 300, 745, 190), (13, 60, 483, 60, 560), (14, 322, 505, 200, 600), (15, 322, 547, 440, 600)], width=4.3)
    called('map-turn', [(1, 1166, 221, 1080, 130), (2, 1400, 400, 1500, 300), (3, 1366, 888, 1560, 940), (4, 900, 440, 760, 330), (5, 640, 640, 480, 560),
                        (6, 70, 700, 200, 760), (7, 1165, 457, 1320, 560), (8, 1090, 115, 900, 60), (9, 380, 950, 560, 1080), (10, 170, 1330, 330, 1260)], width=6.2)
    called('hud', [(1, 512, 22, 610, 22), (2, 690, 45, 780, 80), (3, 520, 150, 420, 110), (4, 700, 207, 800, 250), (5, 495, 295, 400, 300), (6, 512, 270, 600, 320),
                   (7, 130, 320, 220, 380), (8, 120, 192, 60, 150), (9, 895, 320, 800, 380), (10, 910, 192, 965, 150), (11, 90, 490, 220, 470), (12, 512, 545, 640, 520),
                   (13, 512, 595, 380, 610), (14, 905, 458, 800, 500)], width=6.2)
    called('belly', [(1, 512, 45, 760, 80), (2, 512, 320, 620, 250), (3, 375, 195, 280, 140), (4, 90, 548, 230, 500), (5, 940, 548, 800, 500)], width=6.2)
    layout()
    print('figures')
