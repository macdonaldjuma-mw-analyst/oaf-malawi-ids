import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

class IDS_PDF(FPDF):
    def header(self):
        # We will handle custom headers per group in the main loop
        pass

def generate_pdf(raw_data, selected_site, selected_district):
    pdf = IDS_PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    unique_groups = raw_data['GROUP'].unique()
    
    for group in unique_groups:
        pdf.add_page()
        group_df = raw_data[raw_data['GROUP'] == group]
        
        # --- LOGO & HEADER ---
        try:
            pdf.image("oaf_logo.png", x=10, y=8, w=25) # Assumes logo is in your GitHub repo
        except:
            pass # App won't crash if logo is missing
            
        pdf.set_font("Helvetica", 'B', 14)
        pdf.set_x(40)
        pdf.cell(0, 10, f"Main_ID_SR: {selected_site} - Group {group}", ln=True)
        
        pdf.set_font("Helvetica", '', 9)
        pdf.set_x(40)
        pdf.cell(100, 5, f"District: {selected_district} | Site: {selected_site}", ln=True)
        pdf.set_x(40)
        pdf.cell(0, 5, f"Print Date: {pd.Timestamp.now().strftime('%d %b %Y')}", ln=True)
        pdf.ln(15) # Space for the rotated headers
        
        # --- TABLE LOGIC ---
        pivot = group_df.pivot_table(index=['ACCOUNT', 'CLIENT'], columns='SHORTNAME', values='QUANTITY', aggfunc='sum').fillna(0)
        products = list(pivot.columns)
        
        # Fixed Widths
        acc_w = 22
        name_w = 48
        sig_w = 35
        prod_w = 12 # Uniform size for all product columns
        
        # --- ROTATED HEADERS ---
        pdf.set_font("Helvetica", 'B', 7)
        pdf.cell(acc_w, 20, "Account", border=1, align='C')
        pdf.cell(name_w, 20, "Farmer Name", border=1, align='C')
        
        # Capture current position to draw rotated headers
        start_x = pdf.get_x()
        start_y = pdf.get_y()
        
        for prod in products:
            # Draw the box first
            pdf.rect(pdf.get_x(), start_y, prod_w, 20)
            # Rotate and write text
            with pdf.rotation(90, x=pdf.get_x() + (prod_w/2), y=start_y + 10):
                pdf.text(pdf.get_x() + 2, start_y + 18, prod[:15]) 
            pdf.set_x(pdf.get_x() + prod_w)
            
        pdf.cell(sig_w, 20, "Farmer Signature", border=1, align='C', ln=True)
        
        # --- DATA ROWS ---
        pdf.set_font("Helvetica", '', 8)
        for idx, row in pivot.iterrows():
            current_y = pdf.get_y()
            
            # 1. Main Data Row
            pdf.cell(acc_w, 7, str(idx[0]), border='LR') # Left/Right border only
            pdf.cell(name_w, 7, str(idx[1]), border='LR')
            for prod in products:
                val = '1' if row[prod] > 0 else ''
                pdf.cell(prod_w, 7, val, border=1, align='C')
            
            # Draw the SINGLE Signature Box (Heights of both rows combined: 7 + 6 = 13)
            pdf.rect(pdf.get_x(), current_y, sig_w, 13) 
            pdf.set_x(pdf.get_x() + sig_w)
            pdf.ln()
            
            # 2. Adjustment Row (Zebra Stripe)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(acc_w, 6, "", border='LRB', fill=True) # Bottom border added
            pdf.cell(name_w, 6, "  + Adjustment", border='LRB', fill=True)
            for _ in products:
                pdf.cell(prod_w, 6, "", border=1, fill=True)
            
            pdf.ln()
            pdf.set_text_color(0, 0, 0) # Reset black

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
