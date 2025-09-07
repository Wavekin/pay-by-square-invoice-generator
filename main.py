import os
from generator import read_invoice_data, create_invoice

if __name__ == "__main__":
    # Ensure working directory is the script directory
    os.chdir(os.path.dirname(__file__))
    data = read_invoice_data("invoice_data_example.txt")
    create_invoice(data)