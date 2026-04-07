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
        
        # --- HEADER SECTION ---
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 8, f"Delivery: {selected_site} {group}", ln=True)
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(0, 6, f"{selected_site}, {selected_district}", ln=True)
        pdf.cell(0, 6, f"Delivery Date: ________________", ln=True)
        pdf.ln(5)
        
        # --- DATA TABLE ---
        # Get dynamic products for this group
        pivot = group_df.pivot_table(index=['ACCOUNT', 'CLIENT'], columns='SHORTNAME', values='QUANTITY', aggfunc='sum').fillna(0)
        columns = list(pivot.columns)
        
        # Table Header
        pdf.set_font("Helvetica", 'B', 7)
        pdf.cell(20, 10, "Account Number", border=1)
        pdf.cell(45, 10, "Farmer Name", border=1)
        for col in columns:
            pdf.cell(15, 10, col[:8], border=1) # Truncate long names
        pdf.cell(35, 10, "Farmer Signature", border=1)
        pdf.ln()
        
        # Table Rows
        pdf.set_font("Arial", '', 7)
        for idx, row in pivot.iterrows():
            # Data Row
            pdf.cell(20, 8, str(idx[0]), border=1)
            pdf.cell(45, 8, str(idx[1]), border=1)
            for col in columns:
                val = '1' if row[col] > 0 else ''
                pdf.cell(15, 8, val, border=1, align='C')
            pdf.cell(35, 8, "", border=1)
            pdf.ln()
            
            # Adjustment Row
            pdf.set_text_color(150, 150, 150) # Grey color
            pdf.cell(20, 6, "", border=1)
            pdf.cell(45, 6, "  Delivery Adjustment", border=1)
            for col in columns:
                pdf.cell(15, 6, "", border=1)
            pdf.cell(35, 6, "", border=1)
            pdf.ln()
            pdf.set_text_color(0, 0, 0) # Reset to black

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
