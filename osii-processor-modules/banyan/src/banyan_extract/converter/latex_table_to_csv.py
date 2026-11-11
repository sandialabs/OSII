import re

def convert_latex_table_to_csv(latex_string):
    cleaned_table = latex_string
    # Remove the LaTeX table environment and any extra formatting
    #cleaned_table = re.sub(r'\\begin\{tabular\}.*?\\end\{tabular\}', '', latex_string, flags=re.DOTALL)
    cleaned_table = re.sub(r'\\begin\{tabular\}\{[clr ]+\}', '', cleaned_table, flags=re.DOTALL)
    cleaned_table = re.sub(r'\\end\{tabular\}', '', cleaned_table, flags=re.DOTALL)
    cleaned_table = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', cleaned_table)  # Remove LaTeX commands
    cleaned_table = re.sub(r'\{[clr ]+\}', '', cleaned_table)  # Remove LaTeX commands
    cleaned_table = re.sub(r'\\hline', '', cleaned_table)  # Remove horizontal lines
    cleaned_table = re.sub(r'\s+', ' ', cleaned_table)  # Normalize whitespace
    cleaned_table = cleaned_table.strip()

    # Split the table into rows
    rows = cleaned_table.split('\\\\')

    # Create csv friendly datastructure
    cleaned_rows = []
    for row in rows:
        # Split each row into columns based on the '&' character
        columns = row.split('&')
        # Strip whitespace from each column
        columns = [col.strip() for col in columns]
        # Write the row to the CSV file
        cleaned_rows.append(columns)

    return cleaned_rows
