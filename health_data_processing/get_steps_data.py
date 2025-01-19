import xml.etree.ElementTree as ET

def parse_steps_data(xml_content):
    root = ET.fromstring(xml_content)
    steps_data = []

    for record in root.findall(".//Record[@type='HKQuantityTypeIdentifierStepCount']"):
        steps_data.append({
            "start_date": record.get("startDate"),
            "end_date": record.get("endDate"),
            "value": int(record.get("value"))
        })

    return steps_data
