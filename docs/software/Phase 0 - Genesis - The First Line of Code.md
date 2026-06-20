# Phase 0 — Genesis: Friday Labs' First Line of Code

> 📘 **Chapter for Phase 0 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> **Read this first.** It's the story of how the codebase begins — from an empty
> folder to the first line that runs. If you read only one chapter to understand
> *"where does it all start?"*, read this one. No prior robotics knowledge needed.

---

## 1. Why this chapter exists

Every codebase has a first line. Most manuals never tell you what it was, or why.
This one does — because once you understand the **very first decision**, the
whole system makes sense, in order. This is the chapter you hand someone on day
one and say: *"start here, and you'll see how Friday Labs was born."*

---

## 2. The empty folder

In the beginning there is nothing but an empty git repository — a folder the
computer is tracking for changes. No programs, no messages, no rover.

Our software will live in a **workspace**: a folder called `src/` that holds
small projects called **packages**. Right now `src/` doesn't even exist. So the
real question is: **what is the very first thing we create?**

---

## 3. The first decision — *language before behavior*

It's tempting to start with the exciting part: the wheels, the motors, the
brain. That's the wrong first move.

Before a single wheel turns, the parts of the rover need a way to **talk to each
other**. If they can't agree on *how* to talk, nothing else can be built. So the
rule — straight from the dossier, and the way professional robot software (Nav2)
is built — is:

> **Build the shared language first. Behavior second.**

So the first package is not the wheels and not the brain. It's **`friday_msgs`**
— the shared language: the set of message shapes every program will use.

**Design principle #1:** *agree on the language before you write the behavior.*

---

## 4. The first file, and the literal first line of code

The first file we create is:

```
src/friday_msgs/msg/Mark1Header.msg
```

This file defines the **header** — the little identity block that *every* Friday
Labs message carries. After the comment lines that explain it, **the first line
of actual code in the entire project is:**

```
uint8  protocol_major
```

Why is *this* line number one? Because the **very first thing the whole system
must agree on** is *"what version of the language is everyone speaking?"*

- When a new part of the rover tries to join, the Core Hub checks this number.
- If the part's **major** version doesn't match, it's rejected — like turning
  away someone who shows up speaking a language you can't understand.
- Every message, every part, every command is built on top of this one
  agreement.

So the rover's whole conversation begins with a single field that answers *"are
we even speaking the same language?"* That is Friday Labs' first line of code.

---

## 5. Finishing the identity card (the rest of the header)

A version number alone isn't enough. The header grows to five lines — an
**identity card** stamped on every message:

```
uint8  protocol_major     # \
uint8  protocol_minor     #  >  what version of the language (e.g. 0.1.0)
uint16 protocol_patch     # /
string module_id          # WHO is speaking (e.g. MARK1-LOCO-001)
builtin_interfaces/Time stamp   # WHEN it was said
```

Now every message answers three questions automatically: *what language, who,
and when.*

---

## 6. The first useful thing to say — a heartbeat

With an identity card defined, we write the simplest **useful** message a part
can send — `Heartbeat.msg`, which just means *"I'm alive."*

```
Mark1Header header        # the identity card from above
uint64 sequence           # beep #1, #2, #3 ... (proves the timer is running)
uint8  lifecycle_state    # am I starting up, running, or stopping?
```

That's it. A part will send this 5 times a second. The Core Hub listens; if the
beeps stop, it knows that part died.

---

## 7. The first phone call — signing in

Broadcasting (a topic) is one way to talk. The other is a **service** — a
one-time request and answer, like a phone call. The first one is
`RegisterModule.srv` — how a part **signs in** with the boss:

```
Mark1Header header        # who I am + what language I speak
string hardware_type      # e.g. "locomotion"
string[] capabilities     # e.g. ["drive", "steer"]
---                        # (everything below is the answer)
bool   accepted           # did the boss let me in?
string assigned_namespace # the boss gives me my "folder", /mark1/locomotion
string reason
```

---

## 8. The first build — the language becomes real

So far we've only *described* shapes. To turn them into code other programs can
use, we **build** the package:

```bash
colcon build --packages-select friday_msgs
```

Now the language physically exists. You can prove it:

```bash
ros2 interface show friday_msgs/msg/Heartbeat   # prints the shape we wrote
```

**At this point Friday Labs has a language but no behavior — nothing runs yet.**

---

## 9. The first line that actually *runs*

Messages are shapes; they don't *do* anything. The first line of code that truly
**executes** lives in a program's `main()`:

```python
rclpy.init()
```

That single line connects a Python program to the ROS 2 world — it's the spark
that turns a file into a living **node**. Everything that *does* something starts
after that line.

From here the build order is a straight chain:

```
friday_msgs            the language          (Sections 4–8)
    ↓ built on
friday_module_agent    the "part" template   (ModuleAgent: sign in, heartbeat, safe-state)
    ↓ built on
friday_core_hub        the boss              (registry + supervisor + health monitor)
friday_locomotion      the first real part   (subclass of the template)
```

---

## 10. From zero to the first run (reproduce the genesis)

Anyone can re-create Friday Labs' birth in this exact order:

1. **Empty repo** → make the workspace folder `src/`.
2. **`friday_msgs`** — write `Mark1Header.msg` (first line: `uint8 protocol_major`),
   then `Heartbeat`, `HealthStatus`, `ModulePresence`, `RegisterModule.srv`.
3. **`friday_module_agent`** — the QoS rules + the `ModuleAgent` template.
4. **`friday_core_hub`** — the registry, the boss node, the launch file.
5. **`friday_locomotion`** — the first part, built from the template.
6. **Build and run:**
   ```bash
   make build && make run
   ```
   …and you are looking at the **walking skeleton** — see
   [Phase 2 — The Walking Skeleton](Phase 2 - Walking Skeleton.md).

---

## 11. Why the order matters (and can't change)

Look at the dependency chain in Section 9: you **cannot** build the boss before
the language, because the boss *imports* the language. You cannot write a part
before the template it copies. That's why the first line of code had to be inside
`friday_msgs` — and why it had to be the one field everything else checks first:
the protocol version.

> **The whole system is a tree, and `uint8 protocol_major` is its root.**

---

## 12. Where to go next

You've seen the birth. Now read [Phase 2 — The Walking Skeleton](Phase 2 - Walking Skeleton.md)
to watch the system this genesis grew into actually boot, register a part, and
start beating — line by line.

---

**Related:** [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md) ·
[ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) ·
[friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) ·
[Mark 1 Index](../Mark 1 Index.md)
