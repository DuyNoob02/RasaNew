import json
import random
import re
from typing import Any, Optional, Text, Dict, List, Tuple
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from datetime import datetime, timedelta
from dateutil.parser import parse

import requests
import urllib

api = 'http://localhost:5006'


# Dictionary ánh xạ department
DEPARTMENT_MAPPING = {
    "nội tổng hợp": "NoiTH_NoiTru",
    "ngoại tổng hợp": "NgTH_NoiTru",
    "ngoại trú": "NgTru",
    "cấp cứu": "CCHSTC",
    "CSSKSS": "CSSKSS",
    "xét nghiệm":"CLS_XN",
    "cận lâm sàng": "CLS",
    "phẫu thuật":"PT",
    "nội trú":"NoiTru",
    "tài chính": "TaiChinh",
    "nhà thuốc": "NhaThuoc",
    "dược lâm sàng": "DLS",
}

# Dictionary ánh xạ statistic_type
STATISTIC_MAPPING = {
    "nhập viện": "tongNV_",
    "xuất viện": "tongXV_",
    "chuyển viện": "tongCV_",
    "tử vong": "tongTV_",
    "trốn viện": "tongTronVien_",
    "khám bệnh": "tongKCB_",
    "đang điều trị":"tongDDT_",
    "được chỉ định":"tongCD_",
    "thực hiện":"tongTH_",
    "có kết quả": "tongCKQ_",
    "sinh":"tongSinh_",
    "sinh thường": "tongSinhThuong_",
    "sinh mổ": "tongSinhMo_",
    "thu": "tongThu_",
    "chi": "tongChi_"
}



def call_api(field: str, start_date: str, end_date: str) -> int:
    request_data = {
        "startDate": start_date,
        "endDate": end_date,
        "criteria": [field]
    }
    print("Request Data:::::::>", request_data)
    response = requests.post(f"{api}/User/get-totals", json=request_data)

    # Trích xuất dữ liệu JSON từ response
    if response.status_code == 200:
        return response.json()  # Trả về dữ liệu JSON từ API
    else:
        print(f"API Error: {response.status_code}")
        return None  # Trả về None nếu có lỗi

        
def get_start_and_end_dates(value: str, grain: str):
    """
    Trả về ngày bắt đầu và ngày kết thúc dựa trên giá trị thời gian và grain.
    """
    parsed_date = datetime.fromisoformat(value[:-6])  # Bỏ múi giờ '+07:00'
    if grain == "week":
        start_date = parsed_date - timedelta(days=parsed_date.weekday())  # Thứ hai
        end_date = start_date + timedelta(days=6)  # Chủ nhật
    elif grain == "month":
        start_date = parsed_date.replace(day=1)  # Ngày đầu tháng
        next_month = parsed_date.replace(day=28) + timedelta(days=4)  # Chuyển sang tháng kế
        end_date = next_month.replace(day=1) - timedelta(days=1)  # Ngày cuối tháng
    elif grain == "quarter":
        # Xác định quý dựa trên tháng
        quarter = (parsed_date.month - 1) // 3 + 1
        # Tính tháng đầu của quý
        start_month = (quarter - 1) * 3 + 1
        start_date = parsed_date.replace(month=start_month, day=1)  # Ngày đầu quý
        # Tính ngày cuối quý dựa trên quý
        if quarter == 1:
            end_date = parsed_date.replace(year=parsed_date.year, month=3, day=31)
        elif quarter == 2:
            end_date = parsed_date.replace(year=parsed_date.year, month=6, day=30)
        elif quarter == 3:
            end_date = parsed_date.replace(year=parsed_date.year, month=9, day=30)
        else:
            end_date = parsed_date.replace(year=parsed_date.year, month=12, day=31)
    elif grain == "year":
        start_date = parsed_date.replace(month=1, day=1)  # Ngày đầu năm
        end_date = parsed_date.replace(month=12, day=31)  # Ngày cuối năm
    else:
        start_date = parsed_date
        end_date = parsed_date

    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def normalize_report_date(report_type: str, time_str: str) -> Optional[str]:
    """
    Chuẩn hóa định dạng thời gian từ input người dùng sang định dạng DB
    
    Args:
        report_type: Loại báo cáo ('tháng', 'quý', 'ngày', 'năm')
        time_str: Chuỗi thời gian từ người dùng
        
    Returns:
        Chuỗi đã được chuẩn hóa hoặc None nếu không thể xử lý
    """
    print(f"Input time_str: {time_str}")
    print(f"Input report_type: {report_type}")

    def clean_date_part(s: str) -> str:
        print(f"Before clean_date_part: {s}")
        # Chuẩn hóa khoảng trắng thừa trước
        s = re.sub(r'\s+', ' ', s.strip())
        # Chuẩn hóa các dấu phân cách
        s = re.sub(r'\s*[-–—/]\s*', '-', s)
        print(f"After clean_date_part: {s}")
        return s

    def extract_month_year(s: str) -> Tuple[str, str]:
        print(f"Extracting month/year from: {s}")
        patterns = [
            r'.*?tháng\s*(\d{1,2})(?:\s*[-/]\s*|\s+)(?:năm\s*)?(\d{4})',  # Matches both "tháng 10 - 2024" and "tháng 10 năm 2024"
            r'.*?(\d{1,2})(?:\s*[-/]\s*|\s+)(?:năm\s*)?(\d{4})'           # Matches both "10 - 2024" and "10 năm 2024"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, s, re.IGNORECASE)
            if match:
                month, year = match.group(1), match.group(2)
                print(f"Found month: {month}, year: {year}")
                return month, year
        print("No month/year pattern matched")
        return None, None

    def extract_quarter_year(s: str) -> Tuple[str, str]:
        print(f"Extracting quarter/year from: {s}")
        patterns = [
            r'.*?quý\s*(\d{1})(?:\s*[-/]\s*|\s+)(?:năm\s*)?(\d{4})',      # Matches both "quý 1 - 2024" and "quý 1 năm 2024"
            r'.*?q\s*(\d{1})(?:\s*[-/]\s*|\s+)(?:năm\s*)?(\d{4})',        # Matches both "q1 - 2024" and "q1 năm 2024"
            r'.*?(\d{1})(?:\s*[-/]\s*|\s+)(?:năm\s*)?(\d{4})'             # Matches both "1 - 2024" and "1 năm 2024"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, s, re.IGNORECASE)
            if match:
                quarter, year = match.group(1), match.group(2)
                print(f"Found quarter: {quarter}, year: {year}")
                return quarter, year
        print("No quarter/year pattern matched")
        return None, None

    def extract_date(s: str) -> Optional[str]:
        print(f"Extracting date from: {s}")
        patterns = [
            (r'.*?(\d{1,2})(?:\s*[-/]\s*|\s+)(\d{1,2})(?:\s*[-/]\s*|\s+)(\d{4})', r'\1-\2-\3'),  # Matches "27 - 10 - 2024" or "27 10 2024"
            (r'.*?ngày\s*(\d{1,2})(?:\s*[-/]\s*|\s+)?tháng\s*(\d{1,2})(?:\s*[-/]\s*|\s+)?năm\s*(\d{4})', r'\1-\2-\3'),
            (r'.*?(\d{1,2})(?:\s*[-/]\s*|\s+)?tháng\s*(\d{1,2})(?:\s*[-/]\s*|\s+)?năm\s*(\d{4})', r'\1-\2-\3')
        ]
        try:
            dt = parse(s)
            # Chuyển thành định dạng ngày-tháng-năm
            return dt.strftime("%d-%m-%Y")
        except Exception:
            pass
        
        for pattern, replacement in patterns:
            match = re.search(pattern, s)
            if match:
                try:
                    day = int(match.group(1))
                    month = int(match.group(2))
                    year = int(match.group(3))
                    if 1 <= day <= 31 and 1 <= month <= 12:
                        print(f"Found valid date: {day}-{month}-{year}")
                        return f"{day:02d}-{month:02d}-{year}"
                except ValueError:
                    continue
        print("No valid date pattern matched")
        return None

    try:
        # Chuẩn hóa phần thời gian
        time_str = clean_date_part(time_str)
        
        if report_type == "tháng":
            month, year = extract_month_year(time_str)
            if month and year:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    result = f"tháng {month}-{year}"
                    print(f"Normalized result: {result}")
                    return result
                
        elif report_type == "quý":
            quarter, year = extract_quarter_year(time_str)
            if quarter and year:
                quarter_num = int(quarter)
                if 1 <= quarter_num <= 4:
                    result = f"quý {quarter}-{year}"
                    print(f"Normalized result: {result}")
                    return result
                
        elif report_type == "ngày":
            date = extract_date(time_str)
            if date:
                result = f"ngày {date}"
                print(f"Normalized result: {result}")
                return result
                
        elif report_type == "năm":
            match = re.search(r'.*?(\d{4})', time_str)
            if match:
                year = match.group(1)
                result = f"năm {year}"
                print(f"Normalized result: {result}")
                return result
            
        print("No matching pattern found")
        return None
        
    except Exception as e:
        print(f"Error normalizing date: {e}")
        return None


def format_number_with_dot(number: int) -> str:
    """Chuyển số thành chuỗi với dấu chấm phân cách hàng nghìn"""
    return f"{number:,.0f}".replace(",", ".")
class ActionTrackStatistics(Action):
    def name(self) -> Text:
        return "action_track_statistics"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Lấy các thực thể từ thông điệp hiện tại
        current_department = next(tracker.get_latest_entity_values("department"), None)
        current_statistic = next(tracker.get_latest_entity_values("statistic_type"), None)
        print("Current department:", current_department, "Current statistic:", current_statistic)
        last_org_time = tracker.get_slot("last_org_time")
        org_time = last_org_time
        # Lấy thông tin thời gian từ thông điệp
        time_entity = None
        grain = tracker.get_slot("last_grain")  # Giá trị mặc định
        entities = tracker.latest_message.get("entities", [])
        for entity in entities:
            if entity.get("entity") == "time":
                # print("entity:", entity)
                time_entity = entity.get("value")
                org_time = entity.get("text")
                # print("Time Entity:", time_entity)
                grain = entity.get("additional_info", {}).get("grain", "day")
                break

        # Mapping giá trị grain nếu có
        
        # Lấy giá trị từ slots (ngữ cảnh trước đó)
        last_department = tracker.get_slot("last_department")
        last_statistic = tracker.get_slot("last_statistic_type")
        last_time = tracker.get_slot("last_time")
        
        print("Last department:", last_department, "Last statistic:", last_statistic, "Last time:", last_time)
        last_grain = tracker.get_slot("last_grain")

        # Ưu tiên lấy giá trị từ thông điệp hiện tại, nếu không thì lấy từ ngữ cảnh
        department = current_department if current_department else last_department
        statistic_type = current_statistic or last_statistic
        time_entity = time_entity or last_time
        
        print("org_time", org_time)
        grain = grain or last_grain

        # Kiểm tra thông tin bắt buộc
        if not department or not statistic_type or not time_entity:
            missing_info = []
            if not department:
                missing_info.append("phòng ban")
            if not statistic_type:
                missing_info.append("loại thống kê")
            if not time_entity:
                missing_info.append("thời gian")
            
            dispatcher.utter_message(
                text=f"Xin vui lòng cung cấp thêm thông tin về {', '.join(missing_info)} để tôi có thể trả lời chính xác."
            )
            return []

        # Map department và statistic type sang mã truy vấn
        department_code = DEPARTMENT_MAPPING.get(department.lower())
        print("department_code",department_code)
        statistic_code = STATISTIC_MAPPING.get(statistic_type.lower())
        
        if not department_code or not statistic_code:
            dispatcher.utter_message(
                text=f"Xin lỗi, tôi không nhận diện được phòng ban '{department}' hoặc loại thống kê '{statistic_type}'."
            )
            return []

        # Xử lý ngày bắt đầu và ngày kết thúc
        try:
            start_date, end_date = get_start_and_end_dates(time_entity, grain)
            print(f"Start Date: {start_date}, End Date: {end_date}")
        except Exception as e:
            dispatcher.utter_message(text="Không thể xử lý thời gian bạn cung cấp.")
            print(f"Lỗi khi xử lý thời gian: {e}")
            return []
        
        # Tạo truy vấn giả lập
        query_field = f"{statistic_code}{department_code}"
        
        response = call_api(query_field, start_date, end_date)
        print("Response:::::::>", response)
        
        if response:
            for key, value in response.items():
                if isinstance(value, int):  # Kiểm tra nếu giá trị là một số
                    total = format_number_with_dot(value)
                    messages = [
                        f"Trong {org_time.lower()}, tại khoa {department} có {total} bệnh nhân {statistic_type}.",
                        f"{org_time}, khoa {department} đã có {total} bệnh nhân {statistic_type}.",
                        f"Tại khoa {department} {org_time.lower()}, số bệnh nhân {statistic_type} là {total}.",
                        f"Số lượng bệnh nhân {statistic_type} tại khoa {department} trong {org_time.lower()} là {total}.",
                        f"Trong {org_time.lower()} tại khoa {department}, tổng số bệnh nhân {statistic_type} là {total}."
                    ]
                    message = random.choice(messages)
                    dispatcher.utter_message(text=message)  # Trả về thông điệp
                    break  # Chỉ lấy giá trị đầu tiên gặp phải (nếu có nhiều trường chứa số)
            else:
                dispatcher.utter_message(
                    text="Không có số liệu thống kê cho khoảng thời gian này."
                )
        else:
            dispatcher.utter_message(
                text="Không thể lấy thông tin thống kê từ hệ thống, vui lòng thử lại sau."
            )
        
        # Lưu ngữ cảnh hiện tại
        return [
            SlotSet("last_department", department),
            SlotSet("last_statistic_type", statistic_type),
            SlotSet("last_time", time_entity),
            SlotSet("last_grain", grain),
            SlotSet("last_org_time", org_time)
        ]



# Thêm action cho intent ask_statistic_pregnant
class ActionTrackPregnantStatistics(Action):
    def name(self) -> Text:
        return "action_track_pregnant_statistics"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        last_org_time = tracker.get_slot("last_org_time")
        org_time = last_org_time
        # Lấy thực thể thời gian từ thông điệp
        time_entity = None
        grain = tracker.get_slot("last_grain")
        entities = tracker.latest_message.get("entities", [])
        for entity in entities:
            if entity.get("entity") == "time":
                time_entity = entity.get("value")
                org_time = entity.get("text")
                print("Time Entity:", time_entity)
                grain = entity.get("additional_info", {}).get("grain", "day")
                break


        # Lấy thông tin thống kê và phòng ban
        current_statistic = next(tracker.get_latest_entity_values("statistic_type"), None)
        # last_department = tracker.get_slot("last_department")
        last_statistic = tracker.get_slot("last_statistic_type")
        last_time = tracker.get_slot("last_time")
        last_grain = tracker.get_slot("last_grain")
        statistic_type = current_statistic if current_statistic else last_statistic

        # Mặc định department là CSSKSS
        department_code = DEPARTMENT_MAPPING["CSSKSS"]
        statistic_code = STATISTIC_MAPPING.get(statistic_type.lower()) if statistic_type else None
        
        time_entity = time_entity or last_time
        print("Current time:", time_entity, "Grain:", grain)
        grain = grain or last_grain

        # Kiểm tra thông tin đầu vào
        if not statistic_type:
            dispatcher.utter_message(text="Xin lỗi sếp, tôi cần thêm thông tin về loại thống kê như sinh thường, sinh mổ,... để trả lời câu hỏi của sếp.")
            return []

        if not time_entity:
            dispatcher.utter_message(text="Xin lỗi sếp, tôi cần thêm thông tin về thời gian để trả lời câu hỏi của sếp.")

        if not statistic_code:
            dispatcher.utter_message(text=f"Xin lỗi, tôi không thể xử lý yêu cầu thống kê {statistic_type}.")
            return []

        # Xử lý ngày bắt đầu và ngày kết thúc
        try:
            start_date, end_date = get_start_and_end_dates(time_entity, grain)
            print("Start Date:", start_date, "End Date:", end_date)
        except Exception as e:
            dispatcher.utter_message(text="Không thể xử lý thời gian bạn cung cấp.")
            print(f"Lỗi khi xử lý thời gian: {e}")
            return []

        # Tạo mã truy vấn
        query_field = f"{statistic_code}{department_code}"
        
        # TODO: Thực hiện truy vấn API hoặc logic xử lý
        response = call_api(query_field, start_date, end_date)
        print("Response:::::::>", response)
        if response:
            for key, value in response.items():
                if isinstance(value, int):  # Kiểm tra nếu giá trị là một số
                    total = format_number_with_dot(value)
                    messages = [
                        f"Trong {org_time.lower()}, tại khoa sản có {total} sản phụ {statistic_type}.",
                        f"{org_time}, khoa chăm sóc sức khỏe sinh sản đã có {total} sản phụ {statistic_type}.",
                        f"Tại khoa sản {org_time.lower()}, số sản phụ {statistic_type} là {total}.",
                        f"Số lượng sản phụ {statistic_type} tại khoa sản trong {org_time.lower()} là {total}.",
                        f"Trong {org_time.lower()} tại khoa chăm sóc sức khỏe sinh sản, tổng số sản phụ {statistic_type} là {total}."
                    ]
                    message = random.choice(messages)
                    dispatcher.utter_message(text=message)  # Trả về thông điệp
                    break  # Chỉ lấy giá trị đầu tiên gặp phải (nếu có nhiều trường chứa số)
            else:
                dispatcher.utter_message(
                    text="Không có số liệu thống kê cho khoảng thời gian này."
                )
        else:
            dispatcher.utter_message(
                text="Không thể lấy thông tin thống kê từ hệ thống, vui lòng thử lại sau."
            )
        
        # Lưu thông tin vào slots
        return [
            SlotSet("last_statistic_type", statistic_type),
            SlotSet("last_time", time_entity),
            SlotSet("last_grain", grain),
            SlotSet("last_org_time", org_time)
        ]

class ActionGetFinancialStatistics(Action):
    def name(self) -> Text:
        return "action_get_financial_statistics"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Lấy các thực thể từ thông điệp hiện tại
        current_department = next(tracker.get_latest_entity_values("department"), None)
        current_statistic = next(tracker.get_latest_entity_values("statistic_type"), None)
        print("Current department:", current_department, "Current statistic:", current_statistic)
        last_org_time = tracker.get_slot("last_org_time")
        org_time = last_org_time
        # Lấy thông tin thời gian từ thông điệp
        time_entity = None
        grain = tracker.get_slot("last_grain")  # Giá trị mặc định
        entities = tracker.latest_message.get("entities", [])
        for entity in entities:
            if entity.get("entity") == "time":
                # print("entity:", entity)
                time_entity = entity.get("value")
                org_time = entity.get("text")
                # print("Time Entity:", time_entity)
                grain = entity.get("additional_info", {}).get("grain", "day")
                break

        # Mapping giá trị grain nếu có
        
        # Lấy giá trị từ slots (ngữ cảnh trước đó)
        last_department = tracker.get_slot("last_department")
        last_statistic = tracker.get_slot("last_statistic_type")
        print("Last department:", last_department, "Last statistic:", last_statistic)
        last_time = tracker.get_slot("last_time")
        last_grain = tracker.get_slot("last_grain")

        # Ưu tiên lấy giá trị từ thông điệp hiện tại, nếu không thì lấy từ ngữ cảnh
        department = current_department if current_department else last_department
        statistic_type = current_statistic or last_statistic
        time_entity = time_entity or last_time
        grain = grain or last_grain

        # Kiểm tra thông tin bắt buộc
        if not department or not statistic_type or not time_entity:
            missing_info = []
            if not department:
                missing_info.append("phòng ban")
            if not statistic_type:
                missing_info.append("loại thống kê")
            if not time_entity:
                missing_info.append("thời gian")
            
            dispatcher.utter_message(
                text=f"Xin vui lòng cung cấp thêm thông tin về {', '.join(missing_info)} để tôi có thể trả lời chính xác."
            )
            return []

        # Map department và statistic type sang mã truy vấn
        department_code = DEPARTMENT_MAPPING.get(department.lower())
        statistic_code = STATISTIC_MAPPING.get(statistic_type.lower())
        
        if not department_code or not statistic_code:
            dispatcher.utter_message(
                text=f"Xin lỗi, tôi không nhận diện được phòng ban '{department}' hoặc loại thống kê '{statistic_type}'."
            )
            return []

        # Xử lý ngày bắt đầu và ngày kết thúc
        try:
            start_date, end_date = get_start_and_end_dates(time_entity, grain)
            print(f"Start Date: {start_date}, End Date: {end_date}")
        except Exception as e:
            dispatcher.utter_message(text="Không thể xử lý thời gian bạn cung cấp.")
            print(f"Lỗi khi xử lý thời gian: {e}")
            return []
        
        # Tạo truy vấn giả lập
        query_field = f"{statistic_code}{department_code}"
        
        response = call_api(query_field, start_date, end_date)
        print("Response:::::::>", response)
        if response:
            for key, value in response.items():
                if isinstance(value, int):  # Kiểm tra nếu giá trị là một số
                    total = format_number_with_dot(value)
                    messages = [
                        f"Trong {org_time.lower()}, tại {department} {statistic_type} tổng cộng {total} VNĐ.",
                        f"{org_time}, {department} đã {statistic_type} {total} VNĐ.",
                        f"Tại bộ phận {department} {org_time.lower()}, số tiền đã {statistic_type} là {total} VNĐ.",
                        f"Số tiền {statistic_type} tại {department} trong {org_time.lower()} là {total} VNĐ.",
                        f"Trong {org_time.lower()} tại bộ phận {department}, tổng tiền {statistic_type} là {total} VNĐ."
                    ]
                    message = random.choice(messages)
                    # message = f"Từ {start_date} đến {end_date}, tại bộ phận {department} {statistic_type} tổng cộng {total} VNĐ."
                    dispatcher.utter_message(text=message)  # Trả về thông điệp
                    break  # Chỉ lấy giá trị đầu tiên gặp phải (nếu có nhiều trường chứa số)
            else:
                dispatcher.utter_message(
                    text="Không có số liệu thống kê cho khoảng thời gian này."
                )
        else:
            dispatcher.utter_message(
                text="Không thể lấy thông tin thống kê từ hệ thống, vui lòng thử lại sau."
            )
        
        # Lưu ngữ cảnh hiện tại
        return [
            SlotSet("last_department", department),
            SlotSet("last_statistic_type", statistic_type),
            SlotSet("last_time", time_entity),
            SlotSet("last_grain", grain),
            SlotSet("last_org_time", org_time),
        ]
        
        
class ActionFetchReport(Action):
    def name(self) -> str:
        return "action_fetch_report"

    def run(self, dispatcher, tracker, domain):
        # Lấy các entity từ người dùng
        time = next(tracker.get_latest_entity_values("time"), None)
        report = next(tracker.get_latest_entity_values("report_type"), None)
        
        last_report_time = tracker.get_slot("report_time")  # Ví dụ: "ngày 25 tháng 10 - 2024" hoặc "25-10 năm 2024"
        last_report_type = tracker.get_slot("report_type")  # Ví dụ: "tháng", "quý", "năm"
        
        report_time = time if time else last_report_time
        report_type = report if report else last_report_type
        print("Report Time:", report_time, "Report Type:", report_type)

        # Kiểm tra ngữ cảnh cũ từ slot report_context
        current_context = tracker.get_slot("report_context")

        # Nếu ngữ cảnh trước đó có, hiển thị ngữ cảnh cũ
        if current_context is not None:
            try:
                # Kiểm tra xem current_context có phải là chuỗi hay không
                if isinstance(current_context, str):
                    # Nếu là chuỗi, chuyển đổi nó thành dictionary
                    current_context = json.loads(current_context)
            except (json.JSONDecodeError, TypeError) as e:
                # Nếu không thể chuyển đổi, hiển thị thông báo lỗi
                dispatcher.utter_message(
                    text="Có lỗi xảy ra khi đọc ngữ cảnh báo cáo trước đó."
                )
        
        # Kiểm tra Duckling grain (thời gian chính xác)
        duckling_entities = tracker.latest_message.get("entities", [])
        time_grain = next(
            (e.get("additional_info", {}).get("grain") for e in duckling_entities if e["entity"] == "time"),
            None
        )

        # Xác minh loại thời gian khớp với báo cáo
        grain_to_report_type = {
            "month": "tháng",
            "quarter": "quý",
            "year": "năm",
            "day": "ngày"
        }

        # Kiểm tra tính hợp lệ của loại thời gian với báo cáo
        if grain_to_report_type.get(time_grain) != report_type:
            dispatcher.utter_message(
                text=f"Hãy cung cấp thời gian đúng định dạng cho báo cáo {report_type}."
            )
            return []

        normalized_time = normalize_report_date(report_type, report_time)
        print("Normalized Time:", normalized_time)
        if normalized_time:
            report_time = normalized_time
        else:
            dispatcher.utter_message(text=f"Không thể xử lý định dạng thời gian. Vui lòng thử lại với định dạng khác.")
            return []
        print("Normalized Report Time:", report_time)
        # Gọi API tìm báo cáo
        try:
            response = requests.get(f"{api}/api/Reports/GetReportByName", params={"keywords": report_time})
            print("Response:::::::::>", response)
            if response.status_code == 200:
                reports = response.json()
                print(reports)

                # Kiểm tra kết quả từ API
                if reports:
                    report_messages = "\n".join(
                        [f"- {report['reportName']} - [Xem ngay]({report['reportFileUrl']})" for report in reports if report.get('reportFileUrl')]
                    )
                    dispatcher.utter_message(text=f"Các báo cáo bạn cần:\n{report_messages}")
                else:
                    dispatcher.utter_message(text="Không tìm thấy báo cáo phù hợp.")
            else:
                dispatcher.utter_message(text="Lỗi khi truy xuất báo cáo từ hệ thống. Vui lòng thử lại sau.")
        except Exception as e:
            print(f"API Error: {e}")
            dispatcher.utter_message(text="Có lỗi xảy ra khi gọi API. Vui lòng thử lại sau.")

        # Lưu ngữ cảnh hội thoại vào slot report_context
        context_data = {"type": report_type, "time": report_time}
        return [SlotSet("report_context", json.dumps(context_data))]   
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        