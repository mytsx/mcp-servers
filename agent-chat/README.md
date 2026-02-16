# Agent Chat Room MCP Server

Birden fazla Claude Code agent'ının birbirleriyle iletişim kurmasını sağlayan MCP sunucusu. Dosya tabanlı paylaşımlı sohbet odası ile agent'lar mesaj gönderip alabilir.

## Ozellikler

- **Multi-room destegi**: Agent'lar farkli odalarda calisabilir, config degistirmeden room parametresiyle gecis yapar
- Paylasimlı sohbet odası (dosya tabanlı, tüm agent'lar aynı odayı görür)
- Broadcast ve direct mesajlaşma
- Agent katılım/ayrılma takibi
- Mesaj önceliklendirme (urgent/normal/low)
- Stale agent temizleme (5 dk inaktif)
- Thread-safe dosya okuma/yazma (fcntl lock)
- Admin/manager için tüm mesajları okuma

## Kurulum

### Option 1: Using uvx (Recommended)

```json
{
  "mcpServers": {
    "agent-chat": {
      "command": "uvx",
      "args": ["agent-chat-mcp"],
      "env": {
        "AGENT_CHAT_DIR": "/tmp/agent-chat-room",
        "AGENT_CHAT_ROOM": "default"
      }
    }
  }
}
```

### Option 2: Install from Source

```bash
cd agent-chat
pip install -e .
```

## Environment Variables

| Degisken | Varsayilan | Aciklama |
|----------|-----------|----------|
| `AGENT_CHAT_DIR` | `/tmp/agent-chat-room` | Mesaj ve agent verilerinin saklanacagi dizin |
| `AGENT_CHAT_ROOM` | `default` | Varsayilan oda adi (tool parametresiyle override edilebilir) |

## Araclar (Tools)

### `join_room`
Sohbet odasina katil. `room` parametresi ile farkli odalara katilinabilir.
```json
{"agent_name": "backend", "role": "Backend API Developer", "room": "backend-team"}
```

### `send_message`
Mesaj gonder (broadcast veya direct).
```json
{
  "from_agent": "backend",
  "content": "API endpoint'leri hazir",
  "to_agent": "frontend",
  "expects_reply": true,
  "priority": "normal",
  "room": "backend-team"
}
```

### `read_messages`
Yeni mesajlari oku.
```json
{"agent_name": "frontend", "since_id": 5, "unread_only": true, "limit": 10, "room": ""}
```

### `list_agents`
Odadaki agent'lari listele.
```json
{"agent_name": "backend", "room": "backend-team"}
```

### `leave_room`
Odadan ayril.
```json
{"agent_name": "backend", "room": "backend-team"}
```

### `read_all_messages`
Tum mesajlari oku (admin/manager icin).
```json
{"since_id": 0, "limit": 15, "room": ""}
```

### `get_last_message_id`
Son mesaj ID'sini al (polling icin).
```json
{"agent_name": "backend", "room": ""}
```

### `list_rooms`
Mevcut odalari ve agent/mesaj sayilarini listele.
```json
{}
```

### `clear_room`
Odayi temizle (tum mesajlar ve agent kayitlari silinir).
```json
{"room": "backend-team"}
```

## Kullanim Senaryosu

### Multi-Agent Gelistirme (Tek Oda)

3 farkli Claude Code instance'i (terminal) acin:

**Terminal 1 - Backend Agent:**
```
join_room agent_name="backend" role="Backend API Developer"
send_message from_agent="backend" content="REST API endpointleri hazir, /api/users ve /api/posts"
```

**Terminal 2 - Frontend Agent:**
```
join_room agent_name="frontend" role="Frontend React Developer"
read_messages agent_name="frontend"
send_message from_agent="frontend" to_agent="backend" content="users endpoint'inde pagination var mi?"
```

**Terminal 3 - Manager Agent:**
```
join_room agent_name="manager" role="Project Manager"
read_all_messages
```

### Multi-Room Kullanimi

Agent'lar MCP config'i degistirmeden farkli odalara gecis yapabilir:

```
# Varsayilan odaya katil
join_room agent_name="backend" role="Backend Dev"

# Farkli bir odaya da katil
join_room agent_name="backend" role="Backend Dev" room="design-review"

# Farkli odalara mesaj gonder
send_message from_agent="backend" content="API hazir" room="default"
send_message from_agent="backend" content="UI feedback'im var" room="design-review"

# Mevcut odalari listele
list_rooms
```

## Nasil Calisiyor

- Her oda `AGENT_CHAT_DIR/<room_name>/` altinda ayri dizinde saklanir
- Her odanin kendi `messages.json` ve `agents.json` dosyasi vardir
- `room` parametresi bos birakilirsa `AGENT_CHAT_ROOM` env degeri kullanilir (varsayilan: `default`)
- `fcntl` file locking ile thread-safe okuma/yazma
- 5 dakika inaktif agent'lar otomatik temizlenir
- `expects_reply: false` ile sonsuz mesaj dongusu onlenir

## License

MIT
