"""
Mock LLM — Trợ Lý Du Lịch Việt Nam 🇻🇳
Trả lời giả lập (offline, không cần API key) theo từ khóa địa danh/chủ đề du lịch.
Trong production: thay bằng OpenAI/Anthropic khi có API key.
"""
import time
import random


TRAVEL_KB = {
    "hà nội": "🏛️ Hà Nội — thủ đô ngàn năm văn hiến. Nên ghé: Hồ Gươm, Văn Miếu, Phố cổ 36 phố phường, Lăng Bác. Món phải thử: phở, bún chả, cà phê trứng. Đẹp nhất vào mùa thu (tháng 9–11).",
    "sài gòn": "🌆 TP. Hồ Chí Minh (Sài Gòn) — năng động không ngủ. Ghé: Nhà thờ Đức Bà, Chợ Bến Thành, phố đi bộ Nguyễn Huệ, địa đạo Củ Chi. Ăn: cơm tấm, bánh mì, hủ tiếu. Đi được quanh năm.",
    "hồ chí minh": "🌆 TP. Hồ Chí Minh — trung tâm kinh tế sôi động. Ghé: Bưu điện TP, Bảo tàng Chứng tích Chiến tranh, toà Bitexco. Ẩm thực đường phố phong phú: cơm tấm, bánh mì, ốc.",
    "đà nẵng": "🏖️ Đà Nẵng — thành phố đáng sống. Ghé: Bà Nà Hills (Cầu Vàng), bãi biển Mỹ Khê, Ngũ Hành Sơn, cầu Rồng. Gần Hội An & Huế. Đẹp nhất tháng 3–8.",
    "hội an": "🏮 Hội An — phố cổ đèn lồng, di sản UNESCO. Đi bộ phố cổ, thả đèn hoa đăng sông Hoài, may đo quần áo, ăn cao lầu & cơm gà. Lung linh nhất vào buổi tối.",
    "huế": "👑 Huế — cố đô trầm mặc. Ghé: Đại Nội, lăng Tự Đức, lăng Khải Định, chùa Thiên Mụ, sông Hương. Ẩm thực cung đình: bún bò Huế, bánh bèo, cơm hến.",
    "hạ long": "⛰️ Vịnh Hạ Long — kỳ quan thiên nhiên thế giới. Du thuyền ngắm hàng nghìn đảo đá, hang Sửng Sốt, đảo Ti Tốp, chèo kayak. Nên đi 2 ngày 1 đêm trên du thuyền.",
    "sa pa": "🏔️ Sa Pa — thị trấn trong mây. Săn mây, chinh phục Fansipan (nóc nhà Đông Dương), ruộng bậc thang, bản Cát Cát. Đẹp nhất mùa lúa chín (tháng 9).",
    "phú quốc": "🏝️ Phú Quốc — đảo ngọc. Tắm biển Bãi Sao, cáp treo Hòn Thơm, VinWonders, chợ đêm, ngắm hoàng hôn. Đẹp nhất tháng 11–4.",
    "đà lạt": "🌲 Đà Lạt — thành phố ngàn hoa, se lạnh quanh năm. Ghé: hồ Xuân Hương, đồi chè Cầu Đất, thác Datanla, các quán cà phê check-in. Lý tưởng cho cặp đôi.",
    "nha trang": "🌊 Nha Trang — thiên đường biển. Lặn ngắm san hô, VinWonders, tháp Bà Ponagar, tắm bùn khoáng. Hải sản tươi ngon, giá hợp lý.",
    "ninh bình": "🛶 Ninh Bình — 'Hạ Long trên cạn'. Đi thuyền Tràng An, Tam Cốc, leo hang Múa ngắm toàn cảnh, cố đô Hoa Lư. Cảnh non nước hữu tình, gần Hà Nội.",
}

GREETING = "Xin chào! 👋 Mình là Trợ Lý Du Lịch Việt Nam. Bạn muốn khám phá điểm đến nào? Thử hỏi về Hà Nội, Đà Nẵng, Hội An, Hạ Long, Sa Pa, Phú Quốc, Đà Lạt…"
FOOD = "🍜 Ẩm thực Việt Nam tuyệt vời! Must-try: phở, bún chả (Hà Nội), cao lầu (Hội An), bún bò (Huế), cơm tấm (Sài Gòn), mì Quảng (Đà Nẵng). Bạn đang ở vùng nào để mình gợi ý món địa phương?"
BEACH = "🏖️ Biển đẹp Việt Nam: Mỹ Khê (Đà Nẵng), Nha Trang, Phú Quốc, Côn Đảo, Quy Nhơn. Muốn yên tĩnh thì Côn Đảo/Quy Nhơn; muốn sôi động & tiện nghi thì Đà Nẵng/Nha Trang/Phú Quốc."
ITINERARY = "🗺️ Gợi ý lịch trình 4 ngày miền Trung: Ngày 1 Đà Nẵng (Bà Nà, biển Mỹ Khê) → Ngày 2 Hội An (phố cổ, đèn lồng) → Ngày 3 Huế (Đại Nội, lăng tẩm) → Ngày 4 mua sắm & về. Bạn muốn lịch trình cho vùng nào?"
DEFAULT = "🌏 Mình là Trợ Lý Du Lịch Việt Nam. Hãy hỏi mình về một địa danh (vd: 'Đi Đà Nẵng có gì chơi?'), ẩm thực, biển đảo, hoặc lịch trình du lịch nhé!"


def ask(question: str, delay: float = 0.1) -> str:
    """Mock travel assistant — trả lời theo từ khóa."""
    time.sleep(delay + random.uniform(0, 0.05))  # giả lập latency
    q = question.lower()

    for keyword, answer in TRAVEL_KB.items():
        if keyword in q:
            return answer

    if any(w in q for w in ["xin chào", "chào", "hello", "hi ", "alo"]):
        return GREETING
    if any(w in q for w in ["ăn", "món", "ẩm thực", "đặc sản", "food"]):
        return FOOD
    if any(w in q for w in ["biển", "tắm biển", "beach", "đảo"]):
        return BEACH
    if any(w in q for w in ["lịch trình", "mấy ngày", "kế hoạch", "itinerary"]):
        return ITINERARY
    return DEFAULT


def ask_stream(question: str):
    """Mock streaming response — yield từng từ."""
    response = ask(question)
    for word in response.split():
        time.sleep(0.03)
        yield word + " "
