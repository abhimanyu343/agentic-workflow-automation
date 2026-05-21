"""
Automated report generation agent.
Pulls data from configured sources, builds PDF report, emails to stakeholders.
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict
import pandas as pd
from fpdf import FPDF


class ReportGenerator:
    """Generate formatted PDF reports from data sources."""
    
    def __init__(self, title: str, company_name: str = ""):
        self.title = title
        self.company_name = company_name
        self.sections = []
    
    def add_summary(self, metrics: Dict[str, float], period: str = "This Week"):
        self.sections.append({"type": "summary", "metrics": metrics, "period": period})
        return self
    
    def add_table(self, df: pd.DataFrame, section_title: str):
        self.sections.append({"type": "table", "data": df, "title": section_title})
        return self
    
    def add_insight(self, text: str):
        self.sections.append({"type": "insight", "text": text})
        return self
    
    def generate_pdf(self, output_path: str) -> str:
        """Build and save PDF report."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, self.title, ln=True, align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')} | {self.company_name}", ln=True, align="C")
        pdf.ln(8)
        
        for section in self.sections:
            if section["type"] == "summary":
                pdf.set_font("Helvetica", "B", 13)
                pdf.cell(0, 8, f"Executive Summary — {section['period']}", ln=True)
                pdf.set_font("Helvetica", "", 11)
                for key, val in section["metrics"].items():
                    formatted = f"₹{val:,.0f}" if "revenue" in key.lower() else f"{val:.2f}" if isinstance(val, float) else str(val)
                    pdf.cell(0, 7, f"  • {key.replace('_',' ').title()}: {formatted}", ln=True)
                pdf.ln(5)
            
            elif section["type"] == "insight":
                pdf.set_font("Helvetica", "I", 11)
                pdf.set_fill_color(245, 245, 245)
                pdf.multi_cell(0, 7, f"💡 {section['text']}", fill=True)
                pdf.ln(3)
            
            elif section["type"] == "table":
                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(0, 8, section["title"], ln=True)
                pdf.set_font("Helvetica", "", 9)
                df = section["data"].head(10)
                col_w = 180 // len(df.columns)
                for col in df.columns:
                    pdf.cell(col_w, 7, str(col)[:15], border=1)
                pdf.ln()
                for _, row in df.iterrows():
                    for val in row:
                        pdf.cell(col_w, 6, str(val)[:15], border=1)
                    pdf.ln()
                pdf.ln(5)
        
        pdf.output(output_path)
        return output_path
