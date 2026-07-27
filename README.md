# pdf-xfa-tools
This repo contains some low-level Python tools that can be used to inspect and modify PDF forms 
created with Adobe LiveCycle (XFA Forms). These tools were originally developed during the early stages of the [pdf-bullets](https://www.github.com/af-vcd/pdf-bullets) project. 

A reference document that explains the XML syntax for XFA forms in general is found in this repo.

You will also find in the `decos/` folder some premade, 'unlocked' AF decoration forms that can be used 
for drafting decos.

## xfa-extract-all.py

A python script to extract XFA data from a pdf and save them as XML files. 

## xfa-extract-data.py

A python script that extracts only the `datasets` XFA packet from a pdf (the actual form
data) and saves it as `<NomePdf>.xml`, ready to be plugged into Adobe LiveCycle Designer as
a sample data file. Unlike `xfa-extract-all.py`, the output has `<xfa:data>` as its root element
(the `<xfa:datasets>` wrapper is stripped).

## deco-unlock.py

This script takes in an AF Decoration (from vPC) and converts it, making all fields editable and 
allowing the user to switch between font types and stuff

## xfaTools.py

This is a helper python script for easily working with XFA objects within pikepdf. 

## Additional Python Library Dependencies

BeautifulSoup and pikepdf. These can both be easily installed using pip.