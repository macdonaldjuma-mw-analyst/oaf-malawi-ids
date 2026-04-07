import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

class IDS_PDF(FPDF):
    def header(self):
        # We will handle custom headers per group in the main loop
        pass

def generate_pdf(raw_data, selected_site, selected_district):
    # Use Helvetica as it's standard and safe
    pdf = IDS_PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    unique_groups = raw_data['GROUP'].unique()
    
    for group in unique_groups:
        pdf.add_page()
        group_df = raw_data[raw_data['GROUP'] == group]
        
        # --- HEADER SECTION ---
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(0, 10, f"Main_ID_SR: {selected_site} - Group {group}", ln=True, align='C')
        
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(100, 6, f"District: {selected_district}", ln=False)
        pdf.cell(0, 6, f"Site: {selected_site}", ln=True, align='R')
        pdf.cell(0, 6, f"Print Date: {pd.Timestamp.now().strftime('%Y-%m-%d')}", ln=True, align='R')
        pdf.ln(5)
        
        # --- TABLE LOGIC ---
        pivot = group_df.pivot_table(index=['ACCOUNT', 'CLIENT'], columns='SHORTNAME', values='QUANTITY', aggfunc='sum').fillna(0)
        products = list(pivot.columns)
        
        # Calculate Widths: Account (25), Name (50), Signature (35) = 110mm used
        # A4 Landscape is 297mm. Available for products = ~170mm
        prod_col_width = max(12, 170 / len(products)) if products else 15
        
        # Header Row
        pdf.set_fill_color(200, 200, 200) # Light Grey for header
        pdf.set_font("Helvetica", 'B', 8)
        pdf.cell(25, 10, "Account", border=1, fill=True)
        pdf.cell(55, 10, "Farmer Name", border=1, fill=True)
        for prod in products:
            # We rotate or truncate long names
            pdf.cell(prod_col_width, 10, prod[:10], border=1, fill=True, align='C')
        pdf.cell(35, 10, "Signature", border=1, fill=True)
        pdf.ln()
        
        # Data Rows
        pdf.set_font("Helvetica", '', 8)
        for idx, row in pivot.iterrows():
            # Farmer Info
            pdf.cell(25, 8, str(idx[0]), border=1)
            pdf.cell(55, 8, str(idx[1]), border=1)
            
            # Product 1s
            for prod in products:
                val = '1' if row[prod] > 0 else ''
                pdf.cell(prod_col_width, 8, val, border=1, align='C')
            
            pdf.cell(35, 8, "", border=1) # Signature Box
            pdf.ln()
            
            # THE CLEANUP: Adjustment Row with light styling
            pdf.set_fill_color(245, 245, 245) # Very light grey
            pdf.set_text_color(100, 100, 100) # Grey text
            pdf.cell(25, 6, "", border=1, fill=True)
            pdf.cell(55, 6, "  + Delivery Adjustment", border=1, fill=True)
            for _ in products:
                pdf.cell(prod_col_width, 6, "", border=1, fill=True)
            pdf.cell(35, 6, "", border=1, fill=True)
            pdf.ln()
            
            # Reset colors for next farmer
            pdf.set_text_color(0, 0, 0)

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
