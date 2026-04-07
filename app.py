import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

class IDS_PDF(FPDF):
    def header(self):
        # We will handle custom headers per group in the main loop
        pass

def generate_pdf(raw_data, selected_site, selected_district):
    # Initialize PDF in Landscape
    pdf = IDS_PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Define Fixed Column Widths (mm)
    acc_w = 22
    name_w = 48
    prod_w = 12
    sig_w = 35
    
    # Fixed X-Coordinate Map to prevent "text shifting"
    col_map = {
        'acc': 10,
        'name': 10 + acc_w,
        'prod_start': 10 + acc_w + name_w
    }

    unique_groups = raw_data['GROUP'].unique()
    
    for group in unique_groups:
        pdf.add_page()
        group_df = raw_data[raw_data['GROUP'] == group]
        
        # --- LOGO & HEADER ---
        try:
            pdf.image("oaf_logo.png", x=262, y=8, w=25)
        except:
            pass # Skips if logo is not in GitHub repo
            
        pdf.set_font("Helvetica", 'B', 14)
        pdf.set_xy(40, 12)
        pdf.cell(0, 10, f"Main_ID_SR: {selected_site} - Group {group}", ln=True)
        
        pdf.set_font("Helvetica", '', 9)
        pdf.set_x(40)
        pdf.cell(0, 5, f"District: {selected_district} | Site: {selected_site} | Date: {pd.Timestamp.now().strftime('%d %b %Y')}", ln=True)
        
        # --- TABLE HEADER ---
        pdf.set_y(32)
        pdf.set_font("Helvetica", 'B', 8)
        
        # Get products for this specific group
        pivot = group_df.pivot_table(index=['ACCOUNT', 'CLIENT'], columns='SHORTNAME', values='QUANTITY', aggfunc='sum').fillna(0)
        products = list(pivot.columns)
        
        # Draw static headers
        pdf.set_xy(col_map['acc'], 32)
        pdf.cell(acc_w, 20, "Account", border=1, align='C')
        pdf.cell(name_w, 20, "Farmer Name", border=1, align='C')
        
        # --- ROTATED HEADERS ---
        for i, prod in enumerate(products):
            # Calculate the exact left edge of this specific column
            x_pos = col_map['prod_start'] + (i * prod_w)
            
            # 1. Draw the Box
            pdf.rect(x_pos, 32, prod_w, 20)
        
            # 2. Draw the Text (The Pivot must be at x_pos + half the width)
            # We use x_pos + 6 (half of 12) to put the text in the dead center
            with pdf.rotation(90, x=x_pos + 6, y=42):
                pdf.text(x_pos + 2, 50, prod[:15])
        
        # Draw Signature Header (End of products)
        sig_x = col_map['prod_start'] + (len(products) * prod_w)
        pdf.set_xy(sig_x, 32)
        pdf.cell(sig_w, 20, "Farmer Signature", border=1, align='C')
        
        pdf.ln(20) # Move cursor below header block

        # --- DATA ROWS ---
        pdf.set_font("Helvetica", '', 8)
        
        for idx, row in pivot.iterrows():
            # Page Break Check: Each farmer needs 13mm (7+6). If less than 20mm remains, start new page.
            if pdf.get_y() > 180:
                pdf.add_page()
                pdf.set_y(30) # Reset Y after header on new page (Simplified for now)

            y_start = pdf.get_y()
            
            # Row 1: Farmer Data
            pdf.set_xy(col_map['acc'], y_start)
            pdf.cell(acc_w, 7, str(idx[0]), border='LR')
            pdf.cell(name_w, 7, str(idx[1]), border='LR')
            
            for i, prod in enumerate(products):
                pdf.set_xy(col_map['prod_start'] + (i * prod_w), y_start)
                val = '1' if row[prod] > 0 else ''
                pdf.cell(prod_w, 7, val, border=1, align='C')
            
            # Signature Box: Drawn once for both rows (7mm + 6mm = 13mm)
            pdf.set_xy(sig_x, y_start)
            pdf.cell(sig_w, 13, "", border=1) 
            
            # Row 2: Adjustment Row (Stripe)
            y_adj = y_start + 7
            pdf.set_xy(col_map['acc'], y_adj)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(120, 120, 120)
            
            pdf.cell(acc_w, 6, "", border='LRB', fill=True)
            pdf.cell(name_w, 6, "  + Adjustment", border='LRB', fill=True)
            
            for i in range(len(products)):
                pdf.set_xy(col_map['prod_start'] + (i * prod_w), y_adj)
                pdf.cell(prod_w, 6, "", border=1, fill=True)
            
            # Reset for next farmer
            pdf.set_text_color(0, 0, 0)
            pdf.set_xy(col_map['acc'], y_start + 13)

    # --- FINAL OUTPUT ---
    return bytes(pdf.output())

# 1. Establish Snowflake Connection
conn = st.connection("snowflake")

st.title("OAF Malawi: IDS Generator")

# 2. Sidebar Filters (Cascading Logic)
st.sidebar.header("Delivery Filters")

# Helper function to get unique values for filters
@st.cache_data
def get_filter_data(query):
    return conn.query(query)

# --- DISTRICT FILTER (Mandatory) ---
dist_query = "SELECT DISTINCT DISTRICT FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE ORDER BY DISTRICT"
districts = get_filter_data(dist_query)
selected_district = st.sidebar.selectbox("1. Select District", districts, index=None, placeholder="Choose District...")

if selected_district:
    # --- SITE FILTER (Dependent on District) ---
    site_query = f"SELECT DISTINCT SITE FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE WHERE DISTRICT = '{selected_district}' ORDER BY SITE"
    sites = get_filter_data(site_query)
    selected_site = st.sidebar.selectbox("2. Select Site", sites, index=None, placeholder="Choose Site...")

    if selected_site:
        # --- GROUP FILTER (Dependent on Site + "ALL" option) ---
        group_query = f"SELECT DISTINCT \"GROUP\" FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE WHERE SITE = '{selected_site}' ORDER BY \"GROUP\""
        groups_raw = get_filter_data(group_query)
        group_options = ["ALL"] + list(groups_raw['GROUP'].unique())
        selected_group = st.sidebar.selectbox("3. Select Group", group_options, index=0)

        # 3. Pull Data based on selected filters
        group_filter_sql = "" if selected_group == "ALL" else f"AND \"GROUP\" = '{selected_group}'"
        
        main_query = f"""
            SELECT ACCOUNT, CLIENT, \"GROUP\", SHORTNAME, QUANTITY 
            FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE 
            WHERE SITE = '{selected_site}' 
            AND STATUS = 'Undelivered'
            {group_filter_sql}
        """
        raw_data = conn.query(main_query)

        if not raw_data.empty:
            # 4. Processing the Groups for Page Generation
            # We group the dataframe by 'GROUP' to ensure each group can be its own page
            unique_groups_in_data = raw_data['GROUP'].unique()
            
            st.success(f"Found {len(unique_groups_in_data)} groups for {selected_site}")

            for group_name in unique_groups_in_data:
                with st.expander(f"Preview: Group {group_name}", expanded=(selected_group != "ALL")):
                    # Filter data for this specific group
                    group_df = raw_data[raw_data['GROUP'] == group_name]
                    
                    # Pivot logic for the current group
                    pivot_df = group_df.pivot_table(
                        index=['ACCOUNT', 'CLIENT'], 
                        columns='SHORTNAME', 
                        values='QUANTITY', 
                        aggfunc='sum'
                    ).fillna(0)

                    # Convert to POD format
                    pod_display = pivot_df.map(lambda x: '1' if x > 0 else '')

                    # Insert Adjustment Rows
                    final_rows = []
                    for idx, row in pod_display.iterrows():
                        row_dict = row.to_dict()
                        row_dict['Account'] = idx[0]
                        row_dict['Farmer Name'] = idx[1]
                        final_rows.append(row_dict)
                        
                        adj_row = {col: '' for col in pod_display.columns}
                        adj_row['Account'] = ''
                        adj_row['Farmer Name'] = '— Delivery Adjustment'
                        final_rows.append(adj_row)

                    final_ids = pd.DataFrame(final_rows)
                    st.dataframe(final_ids, use_container_width=True)

            # 5. Final Download Button
            st.divider()
            if st.button(f"Download IDS PDF"):
                pdf_bytes = generate_pdf(raw_data, selected_site, selected_district)
                st.download_button(
                    label="Click here to save PDF",
                    data=pdf_bytes,
                    file_name=f"IDS_{selected_site}.pdf",
                    mime="application/pdf"
                )
        else:
            st.warning(f"No undelivered orders for Group: {selected_group}")
else:
    st.info("Please select a District in the sidebar to begin.")
