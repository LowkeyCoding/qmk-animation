import argparse
import PIL.Image as Image
from PIL import ImageSequence
import numpy as np
import io
import os

parser = argparse.ArgumentParser(
    description="Convert image sequences to qmk compressed OLED animations."
)

parser.add_argument(
    "-o",
    dest="output_file",
    default="animation.h",
    help="Path to output file"
)

parser.add_argument(
    "-t",
    dest="threshold",
    default=50,
    help="Set the threshold for a pixel being turned on or off."
)

parser.add_argument(
    'directory',
    type=str,
    help='Directory of images (.PNG) to convert'
)

class ViableImageError(Exception):
    """exception for when no images is found.
    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class ImageConsistencyError(Exception):
    """exception for when images are not uniform size
    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class Compressor():
    def __init__(self, parser):
        args = parser.parse_args()
        
        self.output_file = args.output_file
        self.directory = args.directory
        self.threshold = args.threshold
        self.animation_size = 0
        self.frame_count = 0
        self.image_size = (0, 0)
        self.file_list = []
        self.c_array = []
        self.change_indexs = []
        self.change_values = []
        self.frame0 = []
        self.output = ""
    
    def compress(self):
        if self.directory[-4:] == ".gif":
            self.load_gif()
        else:
            self.load_image_sequence()
        self.convert_to_C_array()
        self.compress_C_array()
        self.get_stats()
        self.generate_file()

        f = open(self.output_file, "w")
        f.write(self.output)
        f.close()


    def load_gif(self):
        img = Image.open(self.directory)
        self.image_size = img.size
        self.frames = []
        for frame in ImageSequence.Iterator(img):
            array = np.array(
                frame.copy().convert('RGBA').getdata(),
                dtype=np.uint8
            )
            array.reshape(
                frame.size[1],
                frame.size[0],
                4
            )
            self.frames.append(array)
    
    def load_image_sequence(self):
        for root, dirs, files in os.walk(self.directory):
            for file in files:
                if file.endswith(".png"):
                    self.file_list.append(os.path.join(root, file))
        if len(self.file_list) < 0:
            try:
                raise IOError
            except IOError as exc:
                raise ViableImageError('Found no png files within this directory: ', directory) from exc
        
        height = []
        width = []
        modes = []

        for file in self.file_list:
            img = Image.open(file)
            height.append(img.height)
            width.append(img.width)
            img = np.array(img.convert('RGBA'))
            self.frames.append(img)

        if len(set(height, width)) > 2:
            try:
                raise IOError
            except IOError as exc:
                raise ImageConsistencyError('Images in the directory are not a consistent size: ', directory) from exc

        self.image_size = (width[0], height[0])
        
    def convert_to_C_array(self):
        for i in range(0, len(self.frames)):
            self.c_array.append(self.img_to_C_array(self.frames[i]))
    
    def img_to_C_array(self, img):
        data = img.flatten()
        output = ""
        height = self.image_size[1]
        width = self.image_size[0]
        rgba_size = 4
        
        first_byte = True
        for y in range(0, height, 8):
            for x in range(0, width):
                byte = 0
                for z in range(7,-1,-1):
                    index = (y+z)*(width*rgba_size) + (x*rgba_size)
                    avg = ((data[index] + data[index + 1] + data[index + 2]) / 3)
                    # set the bit if pixel is turned on.
                    if avg > self.threshold:
                        byte += np.power(2, z)
                
                bytestr = np.base_repr(byte,base=16)
                while len(bytestr) < 2:
                    bytestr = '0' + bytestr
                bytestr = '0x' + bytestr
                if first_byte:
                    output = bytestr
                    first_byte = False
                else: 
                    output += (', ' + bytestr)
        return output

    def compress_C_array(self):
        # we do this so we can get the changes from the last frames animation to the initial frame
        strs = self.c_array
        strs.append(strs[0])

        change_indexs = []
        change_values = []
        change_range = [0,]
        last_change_index = 0
        # we do not want to modify the base frame
        for i in range(1, len(strs)):
            str1 = strs[i-1].replace(' ','').split(',')
            str2 = strs[i].replace(' ','').split(',')
            for x in range(0, len(str2)):
                if str1[x] != str2[x]:
                    change_indexs.append(x)
                    change_values.append(str2[x])
                    last_change_index = len(change_values)
            change_range.append(last_change_index)

        self.frame0 = strs[0].replace(' ','').split(',')
        # lets cut that down by around 43% by only using the bits required to store the changes
        self.change_indexs = self.compress_array(change_indexs)
        self.change_range = self.compress_array(change_range)
        self.change_values = change_values
    
    def compress_array(self, array):
        # First we get the largest number
        _max = max(array)
        # Then we get the amount of bits needed to represent the number
        bit_size = len(bin(_max)[2:])
        output = "0b"
        split_index = 0
        for i in range(0, len(array)):
            bytestr = np.base_repr(array[i], base = 2, padding = 0) 
            while len(bytestr) < 9:
                bytestr = '0' + bytestr
            for j in range(0, 9):
                if(split_index > 7):
                    split_index = 0
                    output += ", 0b"
                output += bytestr[j]
                split_index += 1
        while(split_index <= 7):
            output += "0"
            split_index += 1
        return (output+",", bit_size)

    def get_stats(self):
        self.animation_size = len(self.frame0)
        self.frame_count = len(self.c_array)
        changes_size = len(self.change_indexs[0].split(','))
        changes_size += len(self.change_values)
        changes_size += len(self.change_range[0].split(','))
        self.total_memory = self.animation_size + changes_size
        self.raw_mem_size = (len(self.c_array) - 1)*len(self.frame0)
    
    def generate_file(self):
        self.output += "//**************************************************\n"
        self.output += "//* PLACE THESE VARIABLE DEFS AT BEGINNING OF FILE *\n"
        self.output += "//**************************************************\n\n"

        self.output += f"#define ANIM_SIZE {self.animation_size}\n"
        self.output += f"#define IDLE_FRAMES {self.frame_count}\n"
        self.output += "#define ANI_BYTE_SIZE 8\n"
        self.output += "#define COPY_BIT(dest, id, src, is) dest = (( dest & ~(1<<id) ) | ((src & (1<<is))>>is) << id );\n\n"
        self.output += "//*********************************************\n"
        self.output += f"//* Compression ratio: {round(self.raw_mem_size/self.total_memory,3)} to 1             *\n"
        self.output += f"//* Estimated PROGMEM Usage: {self.total_memory} bytes        *\n"
        self.output += "//*********************************************\n\n"
        
        self.output += "static const char PROGMEM frame[] = {\n"
        self.array_to_string(self.frame0)

        self.output += "\nstatic const uint8_t cumsum_inds[] = {\n"
        self.array_to_string(self.change_range[0].replace(' ','').split(','))

        self.output += "\nstatic const  uint8_t change_inds[] = {\n"
        self.array_to_string(self.change_indexs[0].replace(' ','').split(','))
        
        self.output += "\nstatic const char PROGMEM change_vals[] = {\n"
        self.array_to_string(self.change_values)
        
        self.output += "\nstatic uint64_t get_num(const uint8_t* arr, int bitsize, int index){\n"
        self.output += "\tint arr_index = ((bitsize*index)/ANI_BYTE_SIZE)-1;\n"
        self.output += "\tint byte_index = 7-(((bitsize*index) % ANI_BYTE_SIZE)-1);\n"
        self.output += "\tuint64_t res = 0;\n"
        self.output += "\tfor(int i = bitsize-1;i >= 0; i--){\n"
        self.output += "\t\tCOPY_BIT(res, i, arr[arr_index], byte_index);\n"
        self.output += "\t\tbyte_index--;\n"
        self.output += "\t\tif(byte_index < 0){\n"
        self.output += "\t\t\tbyte_index = 7;\n"
        self.output += "\t\t\tarr_index++;\n"
        self.output += "\t\t}\n\t}\n"
        self.output += "\treturn res;\n}\n\n"

        self.output += "uint16_t index_start = 0;\n"
        self.output += "uint16_t index_end = 0;\n\n"
        self.output += "static void change_frame_bytewise(uint8_t frame_number){\n"
        self.output += f"\tindex_start = get_num(cumsum_inds, {self.change_range[1]}, frame_number);\n"
        self.output += f"\tindex_end = get_num(cumsum_inds, {self.change_range[1]}, frame_number+1);\n"
        self.output += "\tif (index_start != index_end){\n"
        self.output += "\t\tfor (uint16_t i=index_start; i < index_end; i++){\n"
        self.output += f"\t\t\toled_write_raw_byte(pgm_read_byte(change_vals + i), get_num(change_inds, {self.change_indexs[1]}, i+1));\n"
        self.output += "\t\t}\n\t}\n}\n"

    def array_to_string(self, array):
        self.output += "\t"
        for i in range(0, len(array)):
            if i % 15 == 0 and i != 0:
                self.output += "\n\t"
            if array[i] != '':
                self.output += array[i] + ", "
        self.output += "\n};\n"

compressor = Compressor(parser)

compressor.compress()
