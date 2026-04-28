// Scenery layer: loads the pre-generated meadow tile and exposes it
// for tiling by the main editor.  The tile is drawn at half its native
// size so it repeats several times across the visible area.
(function () {
    'use strict';

    // Pixels-per-world-unit used by generate_tile.py.
    const TILE_RES = 2;

    const tileImg = new Image();
    tileImg.src = window.EDITOR_TILE_URL || '/static/tiles/meadow.png';

    // Derive tile world-size from the image's actual pixel dimensions
    // once loaded, so there is no coupling to room size constants.
    tileImg.addEventListener('load', () => {
        window.TE.TILE_W = tileImg.naturalWidth  / TILE_RES / 2;
        window.TE.TILE_H = tileImg.naturalHeight / TILE_RES / 2;
    });

    window.TE.sceneryTile = tileImg;
    window.TE.TILE_W = 0;
    window.TE.TILE_H = 0;
})();
