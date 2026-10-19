(() => {
    const GOV = ["دمشق", "ريف دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب", "درعا", "السويداء", "القنيطرة", "دير الزور", "الرقة", "الحسكة"];
    const REGIONS = ["قامشلو", "الحسكة", "رميلان", "ديرك", "عامودا", "تل تمر", "الشدادي", "الدرباسية"];
    const BRANDS = ["Apple", "Samsung", "Xiaomi", "Huawei", "Oppo", "Infinix", "Tecno", "Nokia", "أخرى"];
    let user = null;
    let favorites = new Set();
    let history = [];
    let searchSequence = 0;

    try {
        const theme = localStorage.getItem("tsy_theme");
        if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    } catch { }

    const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    const api = async (path, options = {}) => {
        const headers = new Headers(options.headers || {});
        if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
        const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
        if (response.status === 204) return null;
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("، ") : body.detail;
            throw new Error(detail || "تعذّر إكمال الطلب، حاول مجدداً");
        }
        return body;
    };
    const normalize = item => ({
        ...item,
        cur: item.currency === "SYP" ? "ل.س" : "$",
        gov: item.city,
        region: item.region || "",
        cond: item.condition === "new" ? "جديد" : "مستعمل",
        desc: item.description,
        seller: item.seller_name,
        phone: item.contact_phone,
        storage: item.storage_gb,
        ram: item.ram_gb,
        sold: item.is_sold,
        owner: item.owner_id,
        created: Date.parse(item.created_at) || 0,
        imgs: item.images || [],
    });
    const priceText = item => `${Number(item.price).toLocaleString("en", { maximumFractionDigits: 2 })} ${item.cur}`;
    const regionOf = item => item.region ? `${item.region}، ${item.gov}` : item.gov || "";
    const formatDate = value => value ? new Date(value).toLocaleString("ar") : "-";
    const message = (element, text, bad = false) => {
        element.textContent = text;
        element.classList.toggle("error", bad);
    };

    window.toast = text => {
        const element = document.createElement("div");
        element.className = "toast glass";
        element.textContent = text;
        document.body.appendChild(element);
        setTimeout(() => element.remove(), 2800);
    };
    window.modal = (title, body, onOk, okText = "تأكيد") => {
        const overlay = document.createElement("div");
        overlay.className = "modal";
        overlay.innerHTML = `<div class="mbox glass"><h3>${esc(title)}</h3>${body}<div class="bar modal-actions"><button class="ghost" data-c>إلغاء</button><button data-o>${esc(okText)}</button></div></div>`;
        document.body.appendChild(overlay);
        overlay.querySelector("[data-c]").addEventListener("click", () => overlay.remove());
        overlay.querySelector("[data-o]").addEventListener("click", async () => {
            try { if (await onOk(overlay) !== false) overlay.remove(); }
            catch (error) { window.toast(error.message); }
        });
        overlay.addEventListener("click", event => { if (event.target === overlay) overlay.remove(); });
    };
    window.toggleTheme = () => {
        const root = document.documentElement;
        const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
        const next = current === "dark" ? "light" : "dark";
        root.dataset.theme = next;
        try { localStorage.setItem("tsy_theme", next); } catch { }
    };
    window.goBack = () => { history.pop(); location.hash = history.pop() || "#/"; };

    function card(item, index = 0) {
        return `<div class="card glass" data-listing-card="${item.id}" role="link" tabindex="0">
            <div class="thumb" data-brand="${esc(item.brand)}">${item.imgs[0] ? `<img loading="lazy" src="${esc(item.imgs[0])}" alt="${esc(item.title)}">` : "📱"}</div>
      <div class="body"><strong>${esc(item.brand)} ${esc(item.model)}</strong>${item.sold ? '<span class="tag sold">تم البيع</span>' : ""}
      <span class="price">${esc(priceText(item))}</span><span class="muted">${esc(regionOf(item))} · ${esc(item.cond)} · ${item.storage} GB${item.ram ? ` · ${item.ram} GB رام` : ""}</span></div></div>`;
    }

    function viewHome(view) {
        view.innerHTML = `<div class="bar glass filter-bar">
            <input id="q" class="search-input" placeholder="ابحث عن الموديل أو الشركة">
      <select id="fb"><option value="">كل الماركات</option>${BRANDS.map(value => `<option>${value}</option>`).join("")}</select>
      <select id="fg"><option value="">كل المحافظات</option>${GOV.map(value => `<option>${value}</option>`).join("")}</select>
    <select id="fr" hidden><option value="">كل المناطق</option>${REGIONS.map(value => `<option>${value}</option>`).join("")}</select>
      <select id="fc"><option value="">جديد ومستعمل</option><option value="new">جديد</option><option value="used">مستعمل</option></select>
      <select id="fcur"><option value="">كل العملات</option><option value="USD">دولار $</option><option value="SYP">ليرة سورية ل.س</option></select>
    <input id="pmin" class="price-input" type="number" min="0" placeholder="أقل سعر">
    <input id="pmax" class="price-input" type="number" min="0" placeholder="أعلى سعر">
      <select id="so"><option value="newest">الأحدث</option><option value="price_asc">السعر: الأقل أولاً</option><option value="price_desc">السعر: الأعلى أولاً</option></select>
    </div><div id="count" class="muted result-count">جارٍ تحميل الإعلانات...</div><div id="list" class="grid"></div>`;
        let timer;
        ["q", "fb", "fg", "fr", "fc", "fcur", "pmin", "pmax", "so"].forEach(id => {
            document.getElementById(id).addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(drawList, 220); });
            document.getElementById(id).addEventListener("change", drawList);
        });
        drawList();
    }

    async function drawList() {
        const box = document.getElementById("list");
        if (!box) return;
        const sequence = ++searchSequence;
        const city = document.getElementById("fg").value;
        const regionControl = document.getElementById("fr");
        regionControl.hidden = city !== "الحسكة";
        const currency = document.getElementById("fcur").value;
        const min = document.getElementById("pmin").value;
        const max = document.getElementById("pmax").value;
        if ((min || max || document.getElementById("so").value !== "newest") && !currency) {
            document.getElementById("count").textContent = "اختر العملة قبل فرز الأسعار أو تحديد نطاقها";
            box.innerHTML = "";
            return;
        }
        const params = new URLSearchParams({ limit: "100", sort: document.getElementById("so").value });
        const values = { q: document.getElementById("q").value.trim(), brand: document.getElementById("fb").value, city, region: city === "الحسكة" ? regionControl.value : "", condition: document.getElementById("fc").value, currency, min_price: min, max_price: max };
        Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); });
        box.innerHTML = '<div class="empty glass">جارٍ تحميل الإعلانات...</div>';
        try {
            const result = await api(`/api/listings?${params}`);
            if (sequence !== searchSequence) return;
            document.getElementById("count").textContent = `${result.length} هاتف`;
            box.innerHTML = result.length ? result.map((item, index) => card(normalize(item), index)).join("") : '<div class="empty glass">لا توجد نتائج مطابقة</div>';
        } catch (error) {
            if (sequence !== searchSequence) return;
            document.getElementById("count").textContent = "تعذّر تحميل الإعلانات";
            box.innerHTML = `<div class="empty glass">${esc(error.message)}</div>`;
        }
    }

    function viewList(view, title, items) {
        view.innerHTML = `<h2>${esc(title)}</h2><div class="muted result-count">${items.length} هاتف</div><div class="grid">${items.length ? items.map((item, index) => card(normalize(item), index)).join("") : '<div class="empty glass">لا توجد هواتف هنا بعد</div>'}</div>`;
    }

    async function viewAd(id, view) {
        view.innerHTML = '<div class="empty glass">جارٍ تحميل الإعلان...</div>';
        try {
            const item = normalize(await api(`/api/listings/${encodeURIComponent(id)}`));
            const imageMarkup = item.imgs.length ? item.imgs.map(url => `<img src="${esc(url)}" alt="${esc(item.title)}">`).join("") : `<div class="thumb thumb-detail" data-brand="${esc(item.brand)}">📱</div>`;
            const whatsapp = item.phone ? `https://wa.me/963${item.phone.replace(/\D/g, "").replace(/^0/, "")}` : "";
            const own = user && user.id === item.owner;
            view.innerHTML = `<div class="panel glass"><div class="gallery">${imageMarkup}</div><h2>${esc(item.brand)} ${esc(item.model)}</h2>
            <div class="price big">${esc(priceText(item))}</div><p>${[item.cond, `${item.storage} GB`, item.ram ? `${item.ram} GB رام` : "", regionOf(item)].filter(Boolean).map(tag => `<span class="tag">${esc(tag)}</span>`).join("")}</p>
        <p>${esc(item.desc)}</p><p class="muted">👁 ${item.views} مشاهدة${item.sold ? " · تم البيع" : ""} · البائع: <a href="#/seller/${encodeURIComponent(item.seller)}">${esc(item.seller)}</a></p>
        <div class="bar">${item.phone ? `<a href="tel:${esc(item.phone)}"><button>اتصال</button></a><a href="${esc(whatsapp)}" target="_blank" rel="noopener"><button class="ghost">واتساب</button></a>` : ""}
        <button class="ghost" data-action="toggle-favorite" data-id="${item.id}">${favorites.has(item.id) ? "♥ محفوظ" : "♡ حفظ"}</button>
        <button class="ghost" data-action="share-listing" data-id="${item.id}">مشاركة</button><button class="ghost" data-action="report-listing" data-id="${item.id}">إبلاغ</button>
        ${own ? `<button class="ghost" data-action="edit-listing" data-id="${item.id}">تعديل</button><button class="ghost" data-action="toggle-sold" data-id="${item.id}">${item.sold ? "إعادة للبيع" : "تم البيع"}</button><button class="danger" data-action="delete-listing" data-id="${item.id}">حذف</button>` : ""}</div></div>`;
        } catch (error) { view.innerHTML = `<div class="empty glass">${esc(error.message)}</div>`; }
    }

    window.toggleFav = async id => {
        if (!user) { location.hash = "#/account"; window.toast("سجّل الدخول لحفظ المفضلة"); return; }
        try {
            if (favorites.has(id)) { await api(`/api/favorites/${id}`, { method: "DELETE" }); favorites.delete(id); }
            else { await api(`/api/favorites/${id}`, { method: "POST" }); favorites.add(id); }
            window.toast(favorites.has(id) ? "أضيف إلى المفضلة" : "أزيل من المفضلة");
            route();
        } catch (error) { window.toast(error.message); }
    };
    window.toggleSold = async id => {
        try { await api(`/api/listings/${id}/sold`, { method: "PATCH" }); window.toast("تم تحديث حالة الإعلان"); route(); }
        catch (error) { window.toast(error.message); }
    };
    window.delAd = async id => {
        if (!confirm("حذف الإعلان نهائياً؟")) return;
        try { await api(`/api/listings/${id}`, { method: "DELETE" }); window.toast("تم حذف الإعلان"); location.hash = "#/"; }
        catch (error) { window.toast(error.message); }
    };
    window.shareAd = async id => {
        const url = `${location.origin}${location.pathname}#/ad/${id}`;
        try { await navigator.clipboard.writeText(url); window.toast("تم نسخ رابط الإعلان"); }
        catch { window.prompt("انسخ رابط الإعلان", url); }
    };
    window.reportAd = id => {
        if (!user) { location.hash = "#/account"; window.toast("سجّل الدخول لإرسال بلاغ"); return; }
        const reasons = ["سعر وهمي", "صور غير صحيحة", "هاتف مسروق", "محتوى مخالف", "أخرى"];
        window.modal("إبلاغ عن الهاتف", `<select data-reason>${reasons.map(reason => `<option>${esc(reason)}</option>`).join("")}</select><textarea data-details rows="3" placeholder="تفاصيل إضافية (اختياري)"></textarea>`, async modal => {
            const response = await api("/api/reports", { method: "POST", body: JSON.stringify({ listing_id: id, reason: modal.querySelector("[data-reason]").value, details: modal.querySelector("[data-details]").value.trim() }) });
            window.toast(response.message);
        }, "إرسال البلاغ");
    };

    function viewAccount(view, notice = "") {
        if (user) {
            view.innerHTML = `<div class="panel glass"><h2>حسابي</h2><p>${esc(user.name)} · ${esc(user.phone)}</p><p class="muted">${esc(user.city || "")} ${user.shop ? `· ${esc(user.shop)}` : ""}</p>
        <div class="bar"><a href="#/sell"><button>نشر هاتف</button></a><button class="ghost" data-action="logout">تسجيل خروج</button></div></div><h3>إعلاناتي</h3><div id="mine" class="grid"><div class="empty glass">جارٍ تحميل إعلاناتك...</div></div>`;
            api("/api/users/me/listings").then(items => {
                const mine = document.getElementById("mine");
                if (mine) mine.innerHTML = items.length ? items.map((item, index) => card(normalize(item), index)).join("") : '<div class="empty glass">لم تنشر أي إعلان بعد</div>';
            }).catch(error => { const mine = document.getElementById("mine"); if (mine) mine.innerHTML = `<div class="empty glass">${esc(error.message)}</div>`; });
            return;
        }
        view.innerHTML = `<div class="panel glass account-panel"><h2 id="at">تسجيل الدخول</h2>${notice ? `<p class="muted">${esc(notice)}</p>` : ""}
            <form id="af" class="form single-column"><div id="nl" class="account-fields" hidden>
        <label>الاسم الكامل<input name="name" minlength="2" required></label><label>اسم المحل (اختياري)<input name="shop" maxlength="120"></label>
        <label>المحافظة<select name="city">${GOV.map(city => `<option>${city}</option>`).join("")}</select></label>
        <label id="register-region" hidden>المنطقة<select name="region">${REGIONS.map(region => `<option>${region}</option>`).join("")}</select></label></div>
        <label>رقم الهاتف<input name="phone" required inputmode="tel" placeholder="09xxxxxxxx"></label>
        <label>كلمة المرور<input name="password" type="password" required minlength="10" autocomplete="current-password"></label>
        <button type="submit" id="asub">دخول</button><a href="#" id="tg">ليس لديك حساب؟ إنشاء حساب</a><span id="amsg" class="muted" role="status"></span></form></div>`;
        let mode = "login";
        const form = document.getElementById("af");
        form.elements.city.addEventListener("change", () => { document.getElementById("register-region").hidden = form.elements.city.value !== "الحسكة"; });
        document.getElementById("tg").addEventListener("click", event => {
            event.preventDefault(); mode = mode === "login" ? "register" : "login";
            const registering = mode === "register";
            document.getElementById("at").textContent = registering ? "إنشاء حساب" : "تسجيل الدخول";
            document.getElementById("nl").hidden = !registering;
            document.getElementById("asub").textContent = registering ? "إنشاء الحساب" : "دخول";
            form.elements.password.autocomplete = registering ? "new-password" : "current-password";
            event.currentTarget.textContent = registering ? "لدي حساب بالفعل" : "ليس لديك حساب؟ إنشاء حساب";
        });
        form.addEventListener("submit", async event => {
            event.preventDefault();
            const submit = document.getElementById("asub");
            const status = document.getElementById("amsg");
            submit.disabled = true; message(status, "جارٍ التحقق...");
            try {
                const body = { phone: form.elements.phone.value.replace(/\s/g, ""), password: form.elements.password.value };
                if (mode === "register") Object.assign(body, { name: form.elements.name.value.trim(), shop: form.elements.shop.value.trim() || null, city: form.elements.city.value, region: form.elements.city.value === "الحسكة" ? form.elements.region.value : null });
                user = await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
                await refreshFavorites(); window.toast(mode === "login" ? "تم تسجيل الدخول" : `أهلاً ${user.name}`); route();
            } catch (error) { message(status, error.message, true); }
            finally { submit.disabled = false; }
        });
    }

    window.logout = async () => {
        try { await api("/api/auth/logout", { method: "POST" }); user = null; favorites.clear(); window.toast("تم تسجيل الخروج"); route(); }
        catch (error) { window.toast(error.message); }
    };

    function viewSell(view, existing = null) {
        if (!user) { viewAccount(view, "سجّل الدخول أولاً لنشر إعلان"); return; }
        const edit = !!existing;
        view.innerHTML = `<div class="panel glass"><h2>${edit ? "تعديل الإعلان" : "نشر هاتف جديد"}</h2><form id="listing-form" class="form">
      <label>الماركة<select name="brand">${BRANDS.map(brand => `<option ${brand === existing?.brand ? "selected" : ""}>${brand}</option>`).join("")}</select></label>
      <label>الموديل<input name="model" required maxlength="100" value="${esc(existing?.model || "")}"></label>
      <label>العملة<select name="currency"><option value="USD" ${existing?.currency === "SYP" ? "" : "selected"}>دولار USD</option><option value="SYP" ${existing?.currency === "SYP" ? "selected" : ""}>ليرة سورية SYP</option></select></label>
      <label>السعر<input name="price" type="number" min="0.01" step="0.01" required value="${esc(existing?.price || "")}"></label>
      <label>سعة التخزين GB<select name="storage_gb">${[16, 32, 64, 128, 256, 512, 1024].map(value => `<option ${value === (existing?.storage_gb || 128) ? "selected" : ""}>${value}</option>`).join("")}</select></label>
      <label>الرام GB<select name="ram_gb"><option value="">غير محدد</option>${[2, 3, 4, 6, 8, 12, 16].map(value => `<option ${value === existing?.ram_gb ? "selected" : ""}>${value}</option>`).join("")}</select></label>
      <label>الحالة<select name="condition"><option value="used" ${existing?.condition === "new" ? "" : "selected"}>مستعمل</option><option value="new" ${existing?.condition === "new" ? "selected" : ""}>جديد</option></select></label>
      <label>المحافظة<select name="city">${GOV.map(city => `<option ${city === existing?.city ? "selected" : ""}>${city}</option>`).join("")}</select></label>
    <label id="listing-region" ${existing?.city === "الحسكة" ? "" : "hidden"}>المنطقة<select name="region">${REGIONS.map(region => `<option ${region === existing?.region ? "selected" : ""}>${region}</option>`).join("")}</select></label>
      <label>اسم البائع<input name="seller_name" required maxlength="120" value="${esc(existing?.seller_name || user.name)}"></label>
      <label>رقم التواصل<input name="contact_phone" required pattern="09[0-9]{8}" inputmode="tel" value="${esc(existing?.contact_phone || user.phone)}"></label>
      <label class="full">الوصف<textarea name="description" maxlength="5000" rows="3">${esc(existing?.description || "")}</textarea></label>
      <label class="full">صور الإعلان (حتى 5 صور، JPEG أو PNG أو WebP، 5 MB للصورة)<input name="images" type="file" accept="image/jpeg,image/png,image/webp" multiple></label>
    <div class="full" id="prev">${(existing?.images || []).map(url => `<img class="listing-preview-image" src="${esc(url)}" alt="صورة الإعلان">`).join("")}</div>
      <div class="full"><button type="submit">${edit ? "حفظ التعديلات" : "نشر الإعلان"}</button> <span id="listing-msg" class="muted" role="status"></span></div></form></div>`;
        const form = document.getElementById("listing-form");
        form.elements.city.addEventListener("change", () => { document.getElementById("listing-region").hidden = form.elements.city.value !== "الحسكة"; });
        form.elements.images.addEventListener("change", () => {
            const files = [...form.elements.images.files];
            const preview = document.getElementById("prev");
            if (files.length > 5 || files.some(file => file.size > 5 * 1024 * 1024)) { form.elements.images.value = ""; preview.textContent = "الحد الأقصى خمس صور، 5 MB للصورة"; return; }
            preview.innerHTML = files.map(file => `<img class="listing-preview-image" src="${URL.createObjectURL(file)}" alt="معاينة الصورة">`).join("");
        });
        form.addEventListener("submit", async event => {
            event.preventDefault();
            const submit = form.querySelector("button[type=submit]");
            const status = document.getElementById("listing-msg");
            submit.disabled = true; message(status, "جارٍ حفظ الإعلان...");
            const payload = Object.fromEntries(new FormData(form).entries());
            delete payload.images;
            payload.price = String(payload.price);
            payload.storage_gb = Number(payload.storage_gb);
            payload.ram_gb = payload.ram_gb ? Number(payload.ram_gb) : null;
            if (payload.city !== "الحسكة") payload.region = null;
            let item;
            try {
                item = edit
                    ? await api(`/api/listings/${existing.id}`, { method: "PATCH", body: JSON.stringify(payload) })
                    : await api("/api/listings", { method: "POST", body: JSON.stringify(payload) });
                const files = [...form.elements.images.files];
                if (files.length) {
                    const data = new FormData(); files.forEach(file => data.append("files", file));
                    await api(`/api/listings/${item.id}/images`, { method: "POST", body: data });
                }
                window.toast(edit ? "تم حفظ التعديلات" : "تم نشر الإعلان"); location.hash = `#/ad/${item.id}`;
            } catch (error) {
                message(status, item ? `حُفظت بيانات الإعلان لكن لم تُرفع الصور: ${error.message}` : error.message, true);
            } finally { submit.disabled = false; }
        });
    }

    async function viewFavorites(view) {
        if (!user) { viewAccount(view, "سجّل الدخول لعرض إعلاناتك المفضلة"); return; }
        view.innerHTML = '<div class="empty glass">جارٍ تحميل المفضلة...</div>';
        try { const items = await api("/api/favorites"); favorites = new Set(items.map(item => item.id)); viewList(view, "المفضلة", items); }
        catch (error) { view.innerHTML = `<div class="empty glass">${esc(error.message)}</div>`; }
    }

    async function viewAdmin(view) {
        if (user?.role !== "admin") { window.toast("هذه الصفحة للمشرفين فقط"); location.hash = "#/"; return; }
        view.innerHTML = `<div class="panel glass"><h2>لوحة الإدارة</h2><div class="bar">${["الإحصائيات", "المستخدمون", "الإعلانات", "البلاغات", "سجل الإدارة"].map((title, index) => `<button class="ghost" data-admin-tab="${index}">${title}</button>`).join("")}</div><div id="admin-data"><div class="empty">جارٍ التحميل...</div></div></div>`;
        view.querySelectorAll("[data-admin-tab]").forEach(button => button.addEventListener("click", () => drawAdmin(Number(button.dataset.adminTab))));
        await drawAdmin(0);
    }

    async function drawAdmin(tab) {
        const box = document.getElementById("admin-data");
        if (!box) return;
        box.innerHTML = '<div class="empty">جارٍ تحميل البيانات...</div>';
        try {
            let html = "";
            if (tab === 0) {
                const values = await api("/api/admin/stats");
                html = `<div class="grid2">${[["المستخدمون", values.users], ["الإعلانات", values.listings], ["تم بيعها", values.sold], ["البلاغات المفتوحة", values.open_reports]].map(([title, value]) => `<div class="stat glass"><b>${value}</b><span class="muted">${title}</span></div>`).join("")}</div>`;
            } else if (tab === 1) {
                const items = await api("/api/admin/users");
                html = table(["الاسم", "الهاتف", "الدور", "الحالة", "إجراء"], items.map(item => [esc(item.name), esc(item.phone), esc(item.role), item.is_active ? "نشط" : "معطل", `<button class="ghost" data-action="set-user-active" data-id="${item.id}" data-active="${!item.is_active}">${item.is_active ? "تعطيل" : "تفعيل"}</button>`]));
            } else if (tab === 2) {
                const items = await api("/api/listings?limit=100");
                html = table(["الإعلان", "البائع", "المشاهدات", "الحالة", "إجراء"], items.map(item => [`<a href="#/ad/${item.id}">${esc(item.title)}</a>`, esc(item.seller_name), item.views, item.is_sold ? "تم البيع" : "متاح", `<button class="danger" data-action="admin-delete-listing" data-id="${item.id}">حذف</button>`]));
            } else if (tab === 3) {
                const [items, listings] = await Promise.all([api("/api/admin/reports"), api("/api/listings?limit=100")]);
                const names = new Map(listings.map(item => [item.id, item.title]));
                html = table(["الإعلان", "السبب", "التفاصيل", "الحالة", "إجراء"], items.map(item => [esc(names.get(item.listing_id) || "إعلان محذوف"), esc(item.reason), esc(item.details || "-"), esc(item.status), `<button class="ghost" data-action="update-report" data-id="${item.id}" data-status="reviewed">تمت المراجعة</button> <button class="ghost" data-action="update-report" data-id="${item.id}" data-status="dismissed">رفض</button>`]));
            } else {
                const items = await api("/api/admin/actions");
                html = table(["الوقت", "المشرف", "الإجراء", "النوع", "المعرف"], items.map(item => [formatDate(item.created_at), item.admin_id, esc(item.action), esc(item.target_type), esc(item.target_id)]));
            }
            if (box.isConnected) box.innerHTML = html;
            document.querySelectorAll("[data-admin-tab]").forEach(button => button.classList.toggle("on", Number(button.dataset.adminTab) === tab));
        } catch (error) { box.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
    }

    function table(headers, rows) {
        return `<div class="wrap"><table class="tbl"><thead><tr>${headers.map(value => `<th>${esc(value)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td>${value}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${headers.length}" class="muted">لا توجد بيانات</td></tr>`}</tbody></table></div>`;
    }
    window.setUserActive = async (id, active) => { try { await api(`/api/admin/users/${id}/active?active=${active}`, { method: "PATCH" }); drawAdmin(1); } catch (error) { window.toast(error.message); } };
    window.adminDeleteListing = async id => { if (!confirm("حذف الإعلان نهائياً؟")) return; try { await api(`/api/admin/listings/${id}`, { method: "DELETE" }); drawAdmin(2); } catch (error) { window.toast(error.message); } };
    window.updateReport = async (id, status) => { try { await api(`/api/admin/reports/${id}?status_value=${status}`, { method: "PATCH" }); drawAdmin(3); } catch (error) { window.toast(error.message); } };

    async function refreshFavorites() {
        if (!user) { favorites.clear(); return; }
        const items = await api("/api/favorites");
        favorites = new Set(items.map(item => item.id));
    }

    async function route() {
        const hash = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
        const [page = "", ...parts] = hash.split("/");
        const argument = parts.join("/");
        document.querySelectorAll("nav a").forEach(link => link.classList.toggle("on", link.dataset.r === page));
        const view = document.getElementById("view");
        const current = location.hash || "#/";
        if (history[history.length - 1] !== current) history.push(current);
        document.getElementById("adminLink").hidden = user?.role !== "admin";
        try {
            if (page === "ad") await viewAd(argument, view);
            else if (page === "edit") {
                if (!user) return viewAccount(view, "سجّل الدخول لتعديل إعلانك");
                const item = await api(`/api/listings/${argument}`);
                if (item.owner_id !== user.id && user.role !== "admin") { window.toast("لا تملك صلاحية تعديل هذا الإعلان"); location.hash = "#/"; return; }
                viewSell(view, item);
            } else if (page === "admin") await viewAdmin(view);
            else if (page === "account") viewAccount(view);
            else if (page === "sell") viewSell(view);
            else if (page === "fav") await viewFavorites(view);
            else if (page === "seller") viewList(view, `إعلانات البائع: ${argument}`, (await api(`/api/listings?seller_name=${encodeURIComponent(argument)}&limit=100`)));
            else viewHome(view);
        } catch (error) { view.innerHTML = `<div class="empty glass">${esc(error.message)}</div>`; }
        if (page && view.isConnected) view.insertAdjacentHTML("afterbegin", '<div class="bar back-bar"><button class="ghost" data-action="go-back">→ رجوع</button></div>');
        window.scrollTo(0, 0);
    }

    document.addEventListener("click", event => {
        const action = event.target.closest("[data-action]");
        if (action) {
            const id = Number(action.dataset.id);
            switch (action.dataset.action) {
                case "home": location.hash = "#/"; break;
                case "toggle-theme": window.toggleTheme(); break;
                case "go-back": window.goBack(); break;
                case "toggle-favorite": window.toggleFav(id); break;
                case "share-listing": window.shareAd(id); break;
                case "report-listing": window.reportAd(id); break;
                case "edit-listing": location.hash = `#/edit/${id}`; break;
                case "toggle-sold": window.toggleSold(id); break;
                case "delete-listing": window.delAd(id); break;
                case "logout": window.logout(); break;
                case "set-user-active": window.setUserActive(id, action.dataset.active === "true"); break;
                case "admin-delete-listing": window.adminDeleteListing(id); break;
                case "update-report": window.updateReport(id, action.dataset.status); break;
            }
            return;
        }
        const card = event.target.closest("[data-listing-card]");
        if (card) location.hash = `#/ad/${card.dataset.listingCard}`;
    });

    document.addEventListener("keydown", event => {
        const card = event.target.closest("[data-listing-card]");
        if (card && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            location.hash = `#/ad/${card.dataset.listingCard}`;
        }
    });

    async function start() {
        try { user = await api("/api/auth/me"); await refreshFavorites(); }
        catch { user = null; favorites.clear(); }
        window.addEventListener("hashchange", route);
        route();
    }

    start();
})();