import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

class IDS_PDF(FPDF):
    def header(self):
        # We will handle custom headers per group in the main loop
        pass

def generate_pdf(raw_data, selected_site, selected_district, del_date, del_tms):
    pdf = IDS_PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Page Settings & Map
    acc_w, name_w, prod_w, sig_w = 22, 48, 12, 35
    col_map = {'acc': 10, 'name': 32, 'prod_start': 80}

    for group in raw_data['GROUP'].unique():
        pdf.add_page()
        group_df = raw_data[raw_data['GROUP'] == group]
        pivot = group_df.pivot_table(index=['ACCOUNT', 'CLIENT'], columns='SHORTNAME', values='QUANTITY', aggfunc='sum').fillna(0)
        products = list(pivot.columns)

        # --- DYNAMIC HEADER HEIGHT ---
        # Find the longest name length. 
        # Every 1 char is ~2mm. Minimum height 20mm.
        max_name_len = max([len(str(p)) for p in products]) if products else 10
        h_height = max(20, (max_name_len * 2) + 5) 

        # --- DOCUMENT HEADER ---
        try: pdf.image("oaf_logo.png", x=262, y=8, w=25)
        except: pass
            
        pdf.set_font("Helvetica", 'B', 11)
        pdf.text(10, 12, f"Delivery: {selected_site} {group}")
        pdf.set_font("Helvetica", '', 9)
        pdf.text(10, 17, f"{selected_site}, {selected_district}")
        pdf.text(10, 22, f"Print Date: {pd.Timestamp.now().strftime('%d %b %Y')}")
        
        # New User-Inputted Fields
        pdf.text(70, 17, f"Delivery Date: {del_date}")
        pdf.text(70, 22, f"Delivery TMS: {del_tms}")
        
        # --- TABLE HEADER (The Fix) ---
        pdf.set_y(28) # Start table exactly here
        pdf.set_font("Helvetica", 'B', 8)
        
        # Static Headers
        pdf.set_xy(col_map['acc'], 28)
        pdf.cell(acc_w, h_height, "Account", border=1, align='C')
        pdf.cell(name_w, h_height, "Farmer Name", border=1, align='C')
        
        # THE FIX: Product Headers
        for i, prod in enumerate(products):
            x_pos = col_map['prod_start'] + (i * prod_w)
            pdf.rect(x_pos, 28, prod_w, h_height)
            
            # Rotation Pivot: 
            # We move y to (28 + h_height - 3) to start text 3mm from bottom line
            with pdf.rotation(90, x=x_pos + (prod_w/2), y=28 + h_height - 3):
                pdf.text(x_pos + 4, 28 + h_height - 2, str(prod))
        
        # Signature Header
        sig_x = col_map['prod_start'] + (len(products) * prod_w)
        pdf.set_xy(sig_x, 28)
        pdf.cell(sig_w, h_height, "Farmer Signature", border=1, align='C')
        pdf.ln(h_height)

        # --- DATA ROWS ---
        pdf.set_font("Helvetica", '', 8)
        for idx, row in pivot.iterrows():
            if pdf.get_y() > 185: pdf.add_page()
            y_s = pdf.get_y()
            
            # Left side
            pdf.set_xy(col_map['acc'], y_s)
            pdf.cell(acc_w, 7, str(idx[0]), border='LR')
            pdf.cell(name_w, 7, str(idx[1]), border='LR')
            
            # Product 1s (Locked to X)
            for i, p in enumerate(products):
                pdf.set_xy(col_map['prod_start'] + (i * prod_w), y_s)
                val = '1' if row[p] > 0 else ''
                pdf.cell(prod_w, 7, val, border=1, align='C')
            
            # Merged Sig Box
            pdf.set_xy(sig_x, y_s)
            pdf.cell(sig_w, 13, "", border=1)
            
            # Adjustment
            pdf.set_xy(col_map['acc'], y_s + 7)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(acc_w, 6, "", border='LRB', fill=True)
            pdf.cell(name_w, 6, "  + Adjustment", border='LRB', fill=True)
            for i in range(len(products)):
                pdf.set_xy(col_map['prod_start'] + (i * prod_w), y_s + 7)
                pdf.cell(prod_w, 6, "", border=1, fill=True)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_xy(col_map['acc'], y_s + 13)

    # --- 1. GRAND TOTAL ROW ---
    pdf.set_fill_color(200, 200, 200) # Darker grey
    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(acc_w + name_w, 8, "SITE TOTALS", border=1, fill=True, align='R')
    
    for prod in products:
        total_qty = (pivot[prod] > 0).sum() # Counts how many '1s' are in the column
        pdf.cell(prod_w, 8, str(int(total_qty)), border=1, fill=True, align='C')
    
    pdf.cell(sig_w, 8, "", border=1, fill=True)
    pdf.ln(15)

    # --- 2. OFFICIAL SIGNATURE SLOTS ---
    pdf.set_font("Helvetica", 'B', 10)
    # Group Leader Slot
    pdf.cell(90, 10, "Group Leader Signature: ________________________", ln=0)
    pdf.cell(40, 10, "Date: ____/____/____", ln=1)
    
    pdf.ln(2)
    
    # Field Officer Slot
    pdf.cell(90, 10, "Field Officer Signature: ________________________", ln=0)
    pdf.cell(40, 10, "Date: ____/____/____", ln=1)

    return bytes(pdf.output())

# 1. Establish Snowflake Connection
conn = st.connection("snowflake")

st.title("OAF Malawi: IDS Generator")

# 2. Sidebar Filters (Cascading Logic)
st.sidebar.header("Delivery Filters")
delivery_date = st.sidebar.date_input("Select Delivery Date")
delivery_tms = st.sidebar.text_input("Enter Delivery TMS", value="TMS-001")

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
                # Pass the new date and TMS variables from your sidebar here:
                pdf_bytes = generate_pdf(raw_data, selected_site, selected_district, delivery_date, delivery_tms)
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
