---
title: Building a Thread-Safe Logger Service from Scratch
date: 2026-06-01
tags: [LLD, Java, Concurrency, Design Patterns]
summary: A complete LLD walkthrough — from "what even is logging?" to async queues and concurrency patterns. Covers immutability, Strategy, Observer, synchronized blocks, LinkedBlockingQueue internals, and producer-consumer architecture.
---

## 1. What is a Logger Service and Why Does Every App Need One?

Imagine you deploy a payment service to production. A user reports their transaction failed. You have no idea why. The database is up, the servers are running — but something went wrong somewhere. How do you find out what happened?

This is exactly why logging exists. A logger service records events as your application runs — what happened, when it happened, and on which thread. These records are written to a console, a file, or a remote storage system so engineers can read them later when something goes wrong.

<div class="realworld">
<strong>Real-world example:</strong> Every time a user logs into LinkedIn, dozens of log lines are written — the request arrived, authentication passed, profile loaded, response sent. If authentication fails, the log line says why. Without logging, debugging production issues is essentially guesswork.
</div>

A good logger service needs to answer three questions at any point in time:

- **What happened?** — the message
- **How serious was it?** — the level (INFO, ERROR, etc.)
- **When and where?** — the timestamp and the thread name

---

## 2. What Are Log Levels and Why Do They Exist?

Not all log messages are equally important. A message that says "user profile loaded successfully" is very different from "database connection lost". Log levels let you express that difference.

| Level | What it means | Example |
|---|---|---|
| `DEBUG` | Detailed internal information, useful during development | "Entering method getUserById with id=42" |
| `INFO` | Normal application events worth recording | "User 42 logged in successfully" |
| `WARN` | Something unexpected happened but the app recovered | "Retry attempt 2 of 3 for payment API" |
| `ERROR` | Something failed — action required | "Payment failed: timeout after 5000ms" |
| `FATAL` | The application cannot continue | "Database connection pool exhausted — shutting down" |

<div class="question">Why not just use a String like "INFO" or "ERROR"? Why assign integers to levels?</div>
<div class="answer">
Integers enable comparison. You need to answer the question: "is this message important enough to log?" That question requires ordering — DEBUG is less important than ERROR. With integer values assigned to each level, you can compare: <code>incomingLevel >= minimumLevel</code>. You cannot do that with plain strings.
</div>

```java
public enum LogLevel {
  DEBUG(1), INFO(2), WARN(3), ERROR(4), FATAL(5);

  private final int level;

  LogLevel(int level) { this.level = level; }

  int getLevel() { return level; }

  public boolean isMinimumLevel(LogLevel threshold) {
    return this.level >= threshold.getLevel();
  }
}
```

So `ERROR.isMinimumLevel(WARN)` returns `true`. `DEBUG.isMinimumLevel(INFO)` returns `false` — filtered out.

---

## 3. The Minimum Level Config — How Real Services Use Levels

Here is something every real production service does: it configures a **minimum log level**. Any message below that level is silently ignored.

<div class="realworld">
<strong>Why this matters in production:</strong> A busy service might handle 10,000 requests per second. If DEBUG logging is on, you could be writing millions of lines per second to disk — slowing down the app and filling up storage in minutes. In production, most services set the minimum level to INFO or WARN. DEBUG is only turned on temporarily when investigating a specific issue.
</div>

This is configured **per destination**. You might have:

- Console → minimum level INFO (normal operation visibility)
- File → minimum level DEBUG (full detail for investigation)
- Alert system → minimum level ERROR (only page on-call for serious issues)

The same log message can go to some destinations and be ignored by others — all based on each destination's configured minimum level.

---

## 4. Designing the Core Data — LogRecord

Before writing any logic, we need a data container that represents a single log entry. This is the **LogRecord**.

<div class="question">Should LogRecord be mutable (setters) or immutable (final fields set in constructor)?</div>
<div class="answer">
Immutable. A log entry is a snapshot of what happened at a specific moment. It should never change after creation. If it were mutable, a bug or a race condition could modify the record mid-flight as it travels from Logger to Destination to Formatter — corrupting your log data.
</div>

<div class="question">Who should capture the timestamp and thread name — the caller, the Logger, or LogRecord's constructor?</div>
<div class="answer">
The <strong>LogRecord constructor itself</strong>. The constructor runs on whichever thread called it — which is always the caller's thread. So <code>Thread.currentThread().getName()</code> gives the correct thread name, and <code>System.currentTimeMillis()</code> gives the exact moment the log was created. If the caller passes these values in, nothing stops them from passing stale or incorrect values.
</div>

<div class="warning">
<strong>The multi-thread trap with mutable construction:</strong> Imagine building LogRecord in multiple steps using setters — <code>record.setTimestamp()</code> then <code>record.setThread()</code> then <code>record.setMessage()</code>. If Thread A is partway through this sequence and the CPU switches to Thread B, Thread A's record could end up with Thread B's values. Immutability with constructor-captured values eliminates this class of bug entirely.
</div>

```java
@Getter
public class LogRecord {
  private final long timeStamp;
  private final String threadName;
  private final String message;
  private final LogLevel logLevel;

  LogRecord(String message, LogLevel logLevel) {
    this.message    = message;
    this.logLevel   = logLevel;
    this.threadName = Thread.currentThread().getName();
    this.timeStamp  = System.currentTimeMillis();
  }
}
```

The `@Getter` annotation (Lombok) generates getters for all fields. No setters — intentionally. Once created, a LogRecord is frozen.

---

## 5. Formatter — The Strategy Pattern

Different destinations need the log in different formats. A file might need JSON so it can be parsed by a log aggregator. A console might need plain readable text. A monitoring system might need XML.

We model this with a **Formatter interface**. Every formatter takes a LogRecord and returns a String — the formatted output ready to write.

<div class="concept">
<strong>Strategy Pattern:</strong> Define a family of algorithms (formatting strategies), put each one in its own class, and make them interchangeable. The caller (Destination) holds a reference to the interface — it never knows or cares which concrete formatter it has.<br><br>
Analogy: your GPS knows it must give directions. You pick the strategy — fastest route, avoid tolls, scenic. Same GPS, swappable strategy. Swap the strategy without changing the GPS.
</div>

```java
public interface Formatter {
  String format(LogRecord logRecord);
}

// Plain text: [2026-06-09 10:23:01] [thread-1] INFO - user logged in
public class TextFormatter implements Formatter {
  @Override
  public String format(LogRecord record) {
    return "[" + record.getTimeStamp() + "] "
         + "[" + record.getThreadName() + "] "
         + record.getLogLevel() + " - "
         + record.getMessage();
  }
}

// JSON: {"timestamp":...,"thread":"thread-1","level":"INFO","message":"user logged in"}
public class JsonFormatter implements Formatter {
  @Override
  public String format(LogRecord record) {
    return "{\"timestamp\":" + record.getTimeStamp()
         + ",\"thread\":\"" + record.getThreadName() + "\""
         + ",\"level\":\"" + record.getLogLevel() + "\""
         + ",\"message\":\"" + record.getMessage() + "\"}";
  }
}
```

---

## 6. Sink — The Physical Writer

A Sink is the component that actually writes bytes somewhere — console, file, network socket. It is intentionally kept thin. A Sink knows nothing about log levels or formatting. It receives a ready-made String and writes it. That is its entire job.

<div class="question">Why keep Sink completely ignorant of formatting and levels?</div>
<div class="answer">
Single responsibility. If Sink knew about formatting, you would need a new Sink class every time you wanted a new format. By keeping Sink dumb, you can combine any Formatter with any Sink freely. ConsoleSink + JsonFormatter, FileSink + TextFormatter, NetworkSink + JsonFormatter — any combination works without changing any class.
</div>

```java
public interface Sink {
  void write(String formatted);
}

public class ConsoleSink implements Sink {
  @Override
  public void write(String formatted) {
    synchronized (this) {
      System.out.println(formatted);
    }
  }
}
```

The `synchronized(this)` block is critical — we will explain exactly why in the concurrency section below.

---

## 7. Destination — Putting It All Together

A Destination is the coordinator. It composes three things:

- A **minimum LogLevel** — the threshold filter
- A **Formatter** — how to format the record
- A **Sink** — where to write it

Example: *ERROR threshold + JsonFormatter + FileSink* = only ERROR and above, in JSON, written to a file.

<div class="question">Why are Sink and Formatter fields final?</div>
<div class="answer">
A Destination's configuration is fixed at startup. You would never swap a FileSink for a ConsoleSink at runtime. <code>final</code> communicates intent — these are not meant to change — and prevents accidental reassignment.
</div>

```java
public class Destination {
  private final LogLevel level;
  private final Sink sink;
  private final Formatter formatter;
  private final LinkedBlockingQueue<LogRecord> queue = new LinkedBlockingQueue<>(1000);

  Destination(LogLevel level, Sink sink, Formatter formatter) {
    this.level     = level;
    this.sink      = sink;
    this.formatter = formatter;

    Thread consumer = new Thread(() -> {
      while (true) {
        try {
          LogRecord record = queue.take();
          if (record.getLogLevel().isMinimumLevel(level))
            sink.write(formatter.format(record));
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          break;
        }
      }
    });
    consumer.start();
  }

  public void send(LogRecord record) {
    queue.offer(record); // non-blocking: drops record if queue is full
  }
}
```

---

## 8. Logger — The Entry Point

Logger is what your application code actually calls. It is the public face of the entire system. Its job is simple:

1. Receive a message and level from the caller
2. Create a LogRecord
3. Broadcast it to every registered Destination

Logger does **not** filter. It does not care about levels. It just creates and broadcasts. Each Destination decides for itself whether to act.

```java
public class Logger {
  private final List<Destination> destinations;

  Logger(List<Destination> destinations) {
    this.destinations = destinations;
  }

  private void log(LogLevel level, String message) {
    LogRecord record = new LogRecord(message, level);
    for (Destination destination : destinations) {
      destination.send(record);
    }
  }

  public void info(String message)  { log(LogLevel.INFO, message); }
  public void error(String message) { log(LogLevel.ERROR, message); }
  public void debug(String message) { log(LogLevel.DEBUG, message); }
  public void warn(String message)  { log(LogLevel.WARN, message); }
}
```

<div class="realworld">
<strong>How you use it:</strong>

```java
Destination consoleDestination = new Destination(LogLevel.INFO, new ConsoleSink(), new JsonFormatter());
Destination fileDestination    = new Destination(LogLevel.DEBUG, new FileSink("app.log"), new TextFormatter());

Logger logger = new Logger(List.of(consoleDestination, fileDestination));

logger.info("User logged in");  // goes to both
logger.debug("Cache miss");     // file only (below INFO for console)
logger.error("DB timeout");     // goes to both
```
</div>

---

## 9. Design Patterns Used — Observer and Strategy

<div class="concept">
<strong>Observer Pattern:</strong> When something happens to me, I notify everyone who cares.<br><br>
<strong>Logger = Subject.</strong> It holds a list of Destinations and broadcasts every LogRecord to all of them.<br>
<strong>Destinations = Observers.</strong> Each one reacts independently based on its own threshold.<br><br>
Analogy: a YouTube channel (subject) uploads a video. All subscribers (observers) get notified. YouTube does not know or care what each subscriber does — watch it, ignore it, share it. Not YouTube's problem. Each subscriber decides independently.
</div>

<div class="concept">
<strong>Strategy Pattern:</strong> I know what to do, but I let someone else decide how.<br><br>
<strong>Formatter is a strategy</strong> — Destination knows it must format, but delegates how to whatever Formatter was injected. Swap JsonFormatter for TextFormatter without touching Destination.<br>
<strong>Sink is a strategy</strong> — Destination knows it must write, but delegates where to whatever Sink was injected. Swap ConsoleSink for FileSink without touching Destination.<br><br>
Analogy: your GPS knows it must give directions. You pick the strategy — fastest, avoid tolls, scenic. Same GPS. Swappable strategy.
</div>

---

## 10. Concurrency — Where Does the Lock Live?

Your application runs with many threads simultaneously. A web server might have 200 HTTP threads all calling `logger.info()` at the same time. What happens?

<div class="question">Each thread creates its own LogRecord. Is that a problem?</div>
<div class="answer">
No. Each thread creates its own LogRecord on its own call stack. There is no sharing between threads here. No race condition, no problem.
</div>

<div class="question">All 200 threads call destination.send() on the same Destination, which eventually calls sink.write(). What is the race condition?</div>
<div class="answer">
If two threads call <code>System.out.println()</code> at the exact same moment, their output can interleave. You might see:<br>
<code>[INFO] user [ERROR] DB down</code><br>
<code>logged in</code><br><br>
Instead of two clean separate lines. This is called output smearing. The write operation is not atomic.
</div>

<div class="question">Where should the lock be placed — in Destination.send() or inside ConsoleSink.write()?</div>
<div class="answer">
Inside <strong>ConsoleSink.write()</strong>. The Sink owns the shared resource — the console output stream. The lock must live with the resource it protects.<br><br>
If you lock inside Destination, and two separate Destination objects share the same ConsoleSink, each Destination locks on its own <code>this</code> — two different locks. They do not protect each other. The race condition remains.
</div>

<div class="question">synchronized method vs synchronized block — what is the difference?</div>
<div class="answer">
<code>synchronized</code> on a method locks the entire method using <code>this</code> as the monitor. A <code>synchronized(this)</code> block lets you lock only the specific critical section — tighter scope, better throughput.<br><br>
In ConsoleSink the only critical operation is println, so both are equivalent here. But in a FileSink that opens a connection, seeks, then writes — you want the lock only around the write, not the setup. Tighter scope = more concurrency.
</div>

<div class="question">When would you choose ReentrantLock over synchronized?</div>
<div class="answer">
When you need features synchronized does not have:
<ul>
<li><code>tryLock(timeout)</code> — try to get the lock, give up after N milliseconds instead of waiting forever</li>
<li><code>lockInterruptibly()</code> — allow a waiting thread to be cancelled</li>
<li><strong>Multiple condition queues</strong> — e.g. "not full" and "not empty" conditions in a bounded queue, where producers wait on one condition and consumers wait on another</li>
</ul>
For a simple Sink, synchronized is correct and cleaner. ReentrantLock shines in async queuing patterns.
</div>

---

## 11. The Problem With Synchronous Logging

In the synchronous version, the caller thread (your HTTP thread) does everything — creates the record, formats it, and waits for the sink to finish writing. If the sink is a slow network or a busy file on disk, the caller thread is blocked the entire time.

```
Thread-1: [business logic: 5ms] [waiting for FileSink lock: 50ms] = 55ms total
Thread-2: [business logic: 5ms] [waiting for FileSink lock: 50ms] = 55ms total
...200 threads all queueing for the same lock
```

In a server handling 10,000 requests per second, logging can become the bottleneck. Threads pile up waiting for the lock. Latency climbs. All because of logging — a side concern that should never impact core business logic.

---

## 12. Async Logging — The BlockingQueue Solution

The fix: decouple the caller from the writer using a queue.

- Caller thread drops the LogRecord into a **LinkedBlockingQueue** and immediately returns
- A dedicated **background thread** drains the queue and calls sink.write()

```
Thread-1: [business logic: 5ms] [queue.offer: 0.1ms] = 5.1ms total ✓
Thread-2: [business logic: 5ms] [queue.offer: 0.1ms] = 5.1ms total ✓
...200 threads all free

Background thread: drains queue, writes to sink at its own pace
```

<div class="question">What data structure should the queue be, and why not a plain ArrayList?</div>
<div class="answer">
A plain ArrayList is not thread-safe. Two threads adding simultaneously can corrupt its internal array. <code>LinkedBlockingQueue</code> is built for concurrent producers and consumers — thread-safe, FIFO ordering preserved, and the consumer thread blocks (sleeps) when the queue is empty instead of spinning and burning CPU.
</div>

<div class="question">LinkedBlockingQueue vs ArrayBlockingQueue — which is better for a logger?</div>
<div class="answer">
<strong>LinkedBlockingQueue uses two separate locks</strong> — one for the head (consumer) and one for the tail (producers). Producers adding records and the consumer reading records never block each other since they operate on opposite ends.<br><br>
<strong>ArrayBlockingQueue uses a single lock</strong> for both operations — a producer must wait if the consumer is active, even though they are touching different ends.<br><br>
For a logger with many producer threads and one consumer, LinkedBlockingQueue gives better throughput.
</div>

<div class="question">Why set a capacity bound on the queue?</div>
<div class="answer">
Without a bound, if producers are faster than the consumer, the queue grows forever and eventually causes an OutOfMemoryError. A bound caps memory usage. When the queue is full, use <code>queue.offer(record)</code> — it returns false and drops the record instead of blocking the caller. The newest record is dropped. Records already in the queue are more valuable.
</div>

<div class="question">Why does the background thread use queue.take() instead of polling in a loop?</div>
<div class="answer">
<code>queue.take()</code> blocks — the thread sleeps when the queue is empty and wakes up the instant a record arrives. Zero CPU waste.<br><br>
A polling loop (<code>while (!queue.isEmpty())</code>) keeps checking constantly even when there is nothing to do, burning a full CPU core for no reason.
</div>

<div class="question">How many background consumer threads do you need?</div>
<div class="answer">
One per Destination. Since <code>sink.write()</code> is synchronized anyway, multiple consumer threads would just queue at that lock — no real parallelism gained. One thread keeps it simple and maintains write order.
</div>

<div class="question">Where is the background thread created?</div>
<div class="answer">
In the Destination constructor. Destination owns the queue, so it owns the thread that drains it. The thread is born when the Destination is created and runs for the application's lifetime.
</div>

---

## 13. Full Architecture Summary

<div class="concept">
<strong>Complete flow for logger.info("user logged in"):</strong><br><br>
1. Logger creates an immutable <strong>LogRecord</strong> — captures message, level, timestamp, thread name<br>
2. Logger broadcasts to all <strong>Destinations</strong> via send() — <em>Observer pattern</em><br>
3. Each Destination puts the record into its own <strong>LinkedBlockingQueue</strong><br>
4. Caller thread is now free — returns immediately<br>
5. Each Destination's background thread <code>take()</code>s from its queue<br>
6. Background thread checks <strong>LogLevel</strong> threshold — skips if below minimum<br>
7. Calls <strong>Formatter</strong>.format() — <em>Strategy pattern</em> — produces a formatted String<br>
8. Calls <strong>Sink</strong>.write() — <code>synchronized</code> block ensures one thread writes at a time
</div>

| Component | Responsibility | Pattern | Key Design Choice |
|---|---|---|---|
| `LogRecord` | Immutable snapshot of one log event | Value Object | Constructor captures thread + timestamp |
| `LogLevel` | Ordered severity enum | — | Integer comparison enables filtering |
| `Formatter` | Converts LogRecord to String | Strategy | Interface — swap JSON/Text without changes |
| `Sink` | Writes String to a physical target | Strategy | Thin interface — knows nothing about levels |
| `Destination` | Composes threshold + Formatter + Sink | Observer (receiver) | Owns queue + background thread |
| `Logger` | Creates LogRecord, broadcasts to all Destinations | Observer (subject) | No filtering — just broadcast |
| `LinkedBlockingQueue` | Decouples caller from writer | Producer-Consumer | Two locks — producers and consumer never block each other |

---

*Written as an LLD interview prep walkthrough — covering immutability, Strategy pattern, Observer pattern, synchronized blocks, ReentrantLock, LinkedBlockingQueue internals, and async producer-consumer logging architecture.*
