# QMK compressed animation
Convert a sequence of PNGS or a GIF to a compressed QMK OLED animation.  

# Usage:

The most basic usage is `python qmk-animation.py <directory | file>`.  
This will generate `animation.h` which contains the animation data and a function to change frames.  

There are to additional arguments you can add `-o <file_path>` and `-t <threshold>`.  
Setting `-o` changes the output file to the one supllied.  
Settung `-t` changes the threshold the average pixel color should be greater than to be considered turned on.

## Include in keymap
First include the animation header at the top of `keymap.c`.
```c
#include "animation.h"
```
Then to render the animation you can add this function.
```c
static int c_frame = 0;
bool first_render = true;

static void render_anim(void) {
    if (first_render) {
        oled_write_raw_P( frame, ANIM_SIZE);
        first_render = 0;
    } else {
        change_frame_bytewise(c_frame);
    }
    c_frame = c_frame+1 > IDLE_FRAMES ? 0 : c_frame+1;
}
```
Then this function can be used in the `oled_task_user` function.
## Set animation speed
To set the animation speed add `#define OLED_UPDATE_INTERVAL <time in ms>` in the file `config.h` inside your keymap folder.


# Credits
[AskMeAboutBirds](https://github.com/AskMeAboutBirds/qmk-oled-animation-compressor) This is mostly a modified version of his code.
