import requests
import time

base = "http://127.0.0.1:5002"
ts = str(int(time.time()))[-6:]
phone_a = "13800000001"
phone_b = "13800000002"

# register landlord A
s1 = requests.Session()
r = s1.post(f"{base}/register", data={
    "name": "房东甲", "phone": phone_a, "wechat_id": "demo_wx",
    "password": "admin123"}, allow_redirects=False)
assert r.status_code == 302 and "/dashboard" in r.headers["Location"], f"register A failed: {r.status_code}"
print("1. register landlord A OK")

# register landlord B
s2 = requests.Session()
r = s2.post(f"{base}/register", data={
    "name": "房东乙", "phone": phone_b, "wechat_id": "",
    "password": "admin123"}, allow_redirects=False)
assert r.status_code == 302, "register B failed"
print("2. register landlord B OK")

# duplicate phone rejected
s3 = requests.Session()
r = s3.post(f"{base}/register", data={"name": "phone_a", "phone": phone_a, "password": "admin123"})
assert "已注册" in r.text or "手机号或密码错误" in r.text, "duplicate phone not rejected"
print("3. duplicate phone rejected OK")

# A creates property
r = s1.post(f"{base}/prop/new", data={
    "name": "甲的房源 2室1厅", "price": "2000", "layout": "2室1厅", "area": "76",
    "floor": "高楼层", "orientation": "朝南", "address": "幸福路1号",
    "descr": "精装两房"}, allow_redirects=False)
assert r.status_code == 302, "create prop failed"
pid_a = int(r.headers["Location"].split("/")[-1])
print("4. landlord A created property", pid_a)

# B creates property
r = s2.post(f"{base}/prop/new", data={"name": "乙的公寓", "price": "1200"},
            allow_redirects=False)
pid_b = int(r.headers["Location"].split("/")[-1])
print("5. landlord B created property", pid_b)

# ownership: B cannot edit A's property (404)
r = s2.get(f"{base}/prop/{pid_a}")
assert r.status_code == 404, "ownership leak!"
r = s1.get(f"{base}/prop/{pid_b}")
assert r.status_code == 404, "ownership leak!"
print("6. ownership isolation OK (cross-access 404)")

# dashboard shows only own properties
r = s1.get(f"{base}/dashboard")
assert "甲的房源" in r.text and "乙的公寓" not in r.text
print("7. dashboard scoped to own properties OK")

# login flow with wrong/right password
s4 = requests.Session()
r = s4.post(f"{base}/login", data={"phone": phone_a, "password": "wrong"})
assert "错误" in r.text
r = s4.post(f"{base}/login", data={"phone": phone_a, "password": "admin123"},
            allow_redirects=False)
assert r.status_code == 302, "login failed"
print("8. login (wrong rejected / right accepted) OK")

# public pages show both properties + owner contact
r = requests.get(f"{base}/")
assert "甲的房源" in r.text and "乙的公寓" in r.text, "public index missing props"
r = requests.get(f"{base}/h/{pid_a}")
assert "房东甲" in r.text and "demo_wx" in r.text and f"tel:{phone_a}" in r.text
print("9. public landing shows owner contact OK")

# spec chips render
assert "2室1厅" in r.text and ">76<" in r.text
print("10. spec chips render OK")

# tenant save → status rented
r = s1.post(f"{base}/prop/{pid_a}/tenant", data={
    "name": "租客小王", "phone": "13600136000", "wechat_id": "wx_tenant",
    "lease_start": "2026-09-01", "lease_end": "2027-09-01"})
r = requests.get(f"{base}/h/{pid_a}")
assert "已出租" in r.text
print("11. tenant save -> rented OK")

# profile update reflects on landing
r = s1.post(f"{base}/profile", data={"name": "房东甲改", "wechat_id": "new_wx",
                                     "old_password": "", "new_password": ""})
r = requests.get(f"{base}/h/{pid_a}")
assert "房东甲改" in r.text and "new_wx" in r.text
print("12. profile update reflects on public page OK")

print("\nALL PLATFORM TESTS PASSED")
