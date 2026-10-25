#!/usr/bin/env python3
"""Generate a small Mope.io-style Java (Swing) game project.

Gameplay modelled on mope.io: you start as a tiny animal, eat berries to gain
XP, evolve into bigger animals, eat smaller animals and run from bigger ones.
Lakes and mud patches slow you down; hold the mouse button or SPACE to sprint.

This is an original, from-scratch implementation inspired by the public
gameplay of mope.io; it uses no assets or code from the original game.

Usage:
    python3 make_mope_project.py [output_dir] [--build] [--run]
"""
import argparse
import subprocess
import sys
from pathlib import Path

PKG = "mopelike"

FILES = {}

FILES["README.md"] = r'''# MopeLike (Java)

A tiny mope.io-inspired game written in plain Java Swing (no dependencies).

## Run
    ./build.sh      # compiles to out/
    ./run.sh        # starts the game

Requires JDK 11+.

## Controls
- Move the mouse: your animal swims/runs toward the cursor
- Hold left mouse button or SPACE: sprint (uses stamina)
- Click / ENTER after dying: respawn

## Rules
- Eat berries to gain XP; you evolve automatically at XP thresholds.
- You can eat any animal of a LOWER tier than yours. Higher tiers eat you.
- Lakes (blue) and mud (brown) slow you down.
'''

FILES["build.sh"] = r'''#!/bin/sh
set -e
cd "$(dirname "$0")"
mkdir -p out
javac -d out $(find src -name '*.java')
echo "Built into ./out"
'''

FILES["run.sh"] = r'''#!/bin/sh
cd "$(dirname "$0")"
[ -d out ] || ./build.sh
exec java -cp out mopelike.Main
'''

FILES["src/mopelike/Main.java"] = r'''package mopelike;

import javax.swing.JFrame;
import javax.swing.SwingUtilities;

public class Main {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("MopeLike");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            GamePanel panel = new GamePanel();
            frame.setContentPane(panel);
            frame.pack();
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
            panel.requestFocusInWindow();
            panel.start();
        });
    }
}
'''

FILES["src/mopelike/AnimalType.java"] = r'''package mopelike;

import java.awt.Color;

/** Evolution tiers. A higher ordinal eats a lower ordinal. */
public enum AnimalType {
    MOUSE("Mouse",   new Color(176, 176, 176), 16, 3.3,    0),
    RABBIT("Rabbit", new Color(235, 220, 205), 20, 3.5,   40),
    DEER("Deer",     new Color(190, 140,  80), 26, 3.7,  150),
    FOX("Fox",       new Color(235, 120,  40), 31, 3.9,  400),
    WOLF("Wolf",     new Color(110, 120, 140), 37, 4.0,  900),
    BEAR("Bear",     new Color( 95,  60,  40), 45, 3.8, 2000),
    DRAGON("Dragon", new Color(190,  50,  60), 56, 4.2, 4500);

    public final String label;
    public final Color color;
    public final double radius;
    public final double speed;
    public final double minXp;

    AnimalType(String label, Color color, double radius, double speed, double minXp) {
        this.label = label;
        this.color = color;
        this.radius = radius;
        this.speed = speed;
        this.minXp = minXp;
    }

    public AnimalType next() {
        AnimalType[] all = values();
        return ordinal() + 1 < all.length ? all[ordinal() + 1] : null;
    }

    public static AnimalType forXp(double xp) {
        AnimalType best = MOUSE;
        for (AnimalType t : values()) {
            if (xp >= t.minXp) best = t;
        }
        return best;
    }
}
'''

FILES["src/mopelike/Food.java"] = r'''package mopelike;

import java.awt.Color;

public class Food {
    public double x, y;
    public final double xp;
    public final Color color;

    public Food(double x, double y, double xp, Color color) {
        this.x = x;
        this.y = y;
        this.xp = xp;
        this.color = color;
    }
}
'''

FILES["src/mopelike/Animal.java"] = r'''package mopelike;

public class Animal {
    public double x, y, vx, vy;
    public double xp;
    public double radius;
    public double stamina = 100;
    public double tx, ty;          // movement target in world coordinates
    public boolean sprint;
    public boolean alive = true;
    public final boolean isPlayer;
    public final String name;
    public AnimalType type;
    // bot wander state
    public double wanderX, wanderY;
    public int wanderTicks;

    public Animal(String name, double x, double y, double xp, boolean isPlayer) {
        this.name = name;
        this.x = x;
        this.y = y;
        this.tx = x;
        this.ty = y;
        this.xp = xp;
        this.isPlayer = isPlayer;
        this.type = AnimalType.forXp(xp);
        this.radius = targetRadius();
    }

    /** Returns true if this gain caused an evolution. */
    public boolean gain(double amount) {
        xp += amount;
        AnimalType t = AnimalType.forXp(xp);
        if (t != type) {
            boolean up = t.ordinal() > type.ordinal();
            type = t;
            return up;
        }
        return false;
    }

    private double targetRadius() {
        AnimalType n = type.next();
        double progress = n == null ? 1 : (xp - type.minXp) / (n.minXp - type.minXp);
        return type.radius + 8 * Math.max(0, Math.min(1, progress));
    }

    public void step(World w) {
        boolean sprinting = sprint && stamina > 1;
        if (sprinting) stamina = Math.max(0, stamina - 0.7);
        else stamina = Math.min(100, stamina + 0.35);

        double dx = tx - x, dy = ty - y;
        double d = Math.hypot(dx, dy);
        double max = type.speed * (sprinting ? 1.6 : 1.0) * w.terrainFactor(x, y);
        double throttle = Math.min(1.0, d / radius);
        double wantX = d > 1 ? dx / d * max * throttle : 0;
        double wantY = d > 1 ? dy / d * max * throttle : 0;
        vx += (wantX - vx) * 0.15;
        vy += (wantY - vy) * 0.15;
        x = Math.max(radius, Math.min(World.W - radius, x + vx));
        y = Math.max(radius, Math.min(World.H - radius, y + vy));
        radius += (targetRadius() - radius) * 0.1;
    }
}
'''

FILES["src/mopelike/World.java"] = r'''package mopelike;

import java.awt.Color;
import java.awt.geom.Ellipse2D;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class World {
    public static final int W = 5000, H = 5000;
    public static final int FOOD_COUNT = 700;
    public static final int BOT_COUNT = 45;
    private static final String[] NAMES = {
        "Pip", "Nibbles", "Moss", "Bramble", "Clover", "Juniper", "Tumble", "Ash",
        "Sprout", "Fern", "Rook", "Willow", "Thistle", "Pebble", "Maple", "Dusk"
    };
    private static final Color[] BERRY = {
        new Color(220, 40, 70), new Color(150, 60, 200), new Color(240, 170, 40)
    };

    public final Random rnd = new Random();
    public final List<Animal> animals = new ArrayList<>();
    public final List<Food> foods = new ArrayList<>();
    public final List<Ellipse2D> lakes = new ArrayList<>();
    public final List<Ellipse2D> mud = new ArrayList<>();
    public Animal player;
    public String message = "";
    public int messageTicks;

    public World() {
        lakes.add(new Ellipse2D.Double(3000, 600, 1500, 1100));
        lakes.add(new Ellipse2D.Double(500, 3300, 1200, 900));
        lakes.add(new Ellipse2D.Double(2400, 3800, 900, 700));
        for (int i = 0; i < 10; i++) {
            double r = 120 + rnd.nextInt(200);
            mud.add(new Ellipse2D.Double(rnd.nextInt(W - 400), rnd.nextInt(H - 400), r * 1.4, r));
        }
        for (int i = 0; i < FOOD_COUNT; i++) foods.add(newFood());
        for (int i = 0; i < BOT_COUNT; i++) animals.add(newBot());
        spawnPlayer("You");
    }

    public void spawnPlayer(String name) {
        player = new Animal(name, W / 2.0 + rnd.nextInt(600) - 300, H / 2.0 + rnd.nextInt(600) - 300, 0, true);
        animals.add(player);
    }

    private Food newFood() {
        Color c = BERRY[rnd.nextInt(BERRY.length)];
        double xp = c == BERRY[2] ? 4 : 2;
        return new Food(rnd.nextDouble() * W, rnd.nextDouble() * H, xp, c);
    }

    private Animal newBot() {
        double xp = Math.pow(rnd.nextDouble(), 3) * 3000;
        return new Animal(NAMES[rnd.nextInt(NAMES.length)], rnd.nextDouble() * W, rnd.nextDouble() * H, xp, false);
    }

    public double terrainFactor(double x, double y) {
        for (Ellipse2D l : lakes) if (l.contains(x, y)) return 0.6;
        for (Ellipse2D m : mud) if (m.contains(x, y)) return 0.75;
        return 1.0;
    }

    public void announce(String msg) {
        message = msg;
        messageTicks = 150;
    }

    public void update() {
        if (messageTicks > 0) messageTicks--;
        for (Animal a : animals) {
            if (!a.isPlayer) Bot.think(this, a);
            a.step(this);
        }
        eatFood();
        eatAnimals();
        while (animals.size() < BOT_COUNT + (player.alive ? 1 : 0)) animals.add(newBot());
    }

    private void eatFood() {
        for (Animal a : animals) {
            for (int i = 0; i < foods.size(); i++) {
                Food f = foods.get(i);
                double dx = f.x - a.x, dy = f.y - a.y;
                if (dx * dx + dy * dy < (a.radius + 5) * (a.radius + 5)) {
                    boolean up = a.gain(f.xp);
                    if (up && a.isPlayer) announce("You evolved into a " + a.type.label + "!");
                    foods.set(i, newFood());
                }
            }
        }
    }

    private void eatAnimals() {
        List<Animal> dead = new ArrayList<>();
        for (Animal a : animals) {
            if (!a.alive) continue;
            for (Animal b : animals) {
                if (a == b || !b.alive || !a.alive) continue;
                if (a.type.ordinal() <= b.type.ordinal()) continue;
                if (Math.hypot(a.x - b.x, a.y - b.y) < a.radius - b.radius * 0.3) {
                    b.alive = false;
                    dead.add(b);
                    boolean up = a.gain(12 + b.xp * 0.4);
                    if (a.isPlayer) {
                        announce("You ate a " + b.type.label + "!");
                        if (up) announce("You evolved into a " + a.type.label + "!");
                    }
                }
            }
        }
        animals.removeAll(dead);
    }
}
'''

FILES["src/mopelike/Bot.java"] = r'''package mopelike;

/** Very small AI: flee bigger animals, chase smaller ones, eat berries, else wander. */
public final class Bot {
    private Bot() {}

    public static void think(World w, Animal me) {
        Animal threat = null, prey = null;
        double threatD = 380, preyD = 320;
        for (Animal o : w.animals) {
            if (o == me || !o.alive) continue;
            double d = Math.hypot(o.x - me.x, o.y - me.y);
            if (o.type.ordinal() > me.type.ordinal() && d < threatD) { threat = o; threatD = d; }
            else if (o.type.ordinal() < me.type.ordinal() && d < preyD) { prey = o; preyD = d; }
        }
        me.sprint = false;
        if (threat != null) {
            me.tx = me.x + (me.x - threat.x) * 3;
            me.ty = me.y + (me.y - threat.y) * 3;
            me.sprint = true;
            return;
        }
        if (prey != null) {
            me.tx = prey.x;
            me.ty = prey.y;
            me.sprint = preyD < 150;
            return;
        }
        Food best = null;
        double bestD = 300;
        for (Food f : w.foods) {
            double d = Math.hypot(f.x - me.x, f.y - me.y);
            if (d < bestD) { bestD = d; best = f; }
        }
        if (best != null) {
            me.tx = best.x;
            me.ty = best.y;
            return;
        }
        if (me.wanderTicks-- <= 0) {
            me.wanderX = Math.max(0, Math.min(World.W, me.x + w.rnd.nextInt(800) - 400));
            me.wanderY = Math.max(0, Math.min(World.H, me.y + w.rnd.nextInt(800) - 400));
            me.wanderTicks = 90 + w.rnd.nextInt(120);
        }
        me.tx = me.wanderX;
        me.ty = me.wanderY;
    }
}
'''

FILES["src/mopelike/GamePanel.java"] = r'''package mopelike;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.geom.Ellipse2D;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import javax.swing.JPanel;
import javax.swing.Timer;

public class GamePanel extends JPanel {
    private static final Color GRASS = new Color(120, 185, 90);
    private static final Color GRID = new Color(0, 0, 0, 25);

    private final World world = new World();
    private final Timer timer = new Timer(16, e -> tick());
    private int mouseX, mouseY;
    private boolean mouseDown, spaceDown;

    public GamePanel() {
        setPreferredSize(new Dimension(1000, 700));
        setFocusable(true);
        addMouseMotionListener(new MouseAdapter() {
            @Override public void mouseMoved(MouseEvent e) { mouseX = e.getX(); mouseY = e.getY(); }
            @Override public void mouseDragged(MouseEvent e) { mouseX = e.getX(); mouseY = e.getY(); }
        });
        addMouseListener(new MouseAdapter() {
            @Override public void mousePressed(MouseEvent e) {
                mouseDown = true;
                if (!world.player.alive) respawn();
            }
            @Override public void mouseReleased(MouseEvent e) { mouseDown = false; }
        });
        addKeyListener(new KeyAdapter() {
            @Override public void keyPressed(KeyEvent e) {
                if (e.getKeyCode() == KeyEvent.VK_SPACE) spaceDown = true;
                if (e.getKeyCode() == KeyEvent.VK_ENTER && !world.player.alive) respawn();
            }
            @Override public void keyReleased(KeyEvent e) {
                if (e.getKeyCode() == KeyEvent.VK_SPACE) spaceDown = false;
            }
        });
    }

    public void start() { timer.start(); }

    private void respawn() { world.spawnPlayer("You"); }

    private double camX() { return world.player.x - getWidth() / 2.0; }
    private double camY() { return world.player.y - getHeight() / 2.0; }

    private void tick() {
        Animal p = world.player;
        if (p.alive) {
            p.tx = mouseX + camX();
            p.ty = mouseY + camY();
            p.sprint = mouseDown || spaceDown;
        }
        world.update();
        repaint();
    }

    @Override
    protected void paintComponent(Graphics g0) {
        Graphics2D g = (Graphics2D) g0.create();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        int cw = getWidth(), ch = getHeight();
        double cx = camX(), cy = camY();

        g.setColor(new Color(40, 70, 40));
        g.fillRect(0, 0, cw, ch);
        g.translate(-cx, -cy);

        g.setColor(GRASS);
        g.fillRect(0, 0, World.W, World.H);
        g.setColor(GRID);
        g.setStroke(new BasicStroke(1));
        int x0 = (int) (cx / 100) * 100, y0 = (int) (cy / 100) * 100;
        for (int x = Math.max(0, x0); x < Math.min(World.W, cx + cw + 100); x += 100) g.drawLine(x, 0, x, World.H);
        for (int y = Math.max(0, y0); y < Math.min(World.H, cy + ch + 100); y += 100) g.drawLine(0, y, World.W, y);

        g.setColor(new Color(110, 80, 50));
        for (Ellipse2D m : world.mud) g.fill(m);
        g.setColor(new Color(60, 130, 210));
        for (Ellipse2D l : world.lakes) g.fill(l);

        for (Food f : world.foods) {
            if (f.x < cx - 20 || f.x > cx + cw + 20 || f.y < cy - 20 || f.y > cy + ch + 20) continue;
            g.setColor(f.color);
            g.fill(new Ellipse2D.Double(f.x - 5, f.y - 5, 10, 10));
        }

        List<Animal> sorted = new ArrayList<>(world.animals);
        sorted.sort(Comparator.comparingDouble(a -> a.radius));
        for (Animal a : sorted) drawAnimal(g, a);

        g.setColor(new Color(0, 0, 0, 120));
        g.setStroke(new BasicStroke(6));
        g.drawRect(0, 0, World.W, World.H);

        g.translate(cx, cy);
        drawHud(g, cw, ch);
        g.dispose();
    }

    private void drawAnimal(Graphics2D g, Animal a) {
        double r = a.radius;
        g.setColor(a.type.color);
        g.fill(new Ellipse2D.Double(a.x - r, a.y - r, r * 2, r * 2));
        g.setColor(a.type.color.darker().darker());
        g.setStroke(new BasicStroke(3));
        g.draw(new Ellipse2D.Double(a.x - r, a.y - r, r * 2, r * 2));

        double ang = Math.atan2(a.ty - a.y, a.tx - a.x);
        for (int s = -1; s <= 1; s += 2) {
            double ex = a.x + Math.cos(ang + s * 0.5) * r * 0.55;
            double ey = a.y + Math.sin(ang + s * 0.5) * r * 0.55;
            g.setColor(Color.WHITE);
            g.fill(new Ellipse2D.Double(ex - r * 0.2, ey - r * 0.2, r * 0.4, r * 0.4));
            g.setColor(Color.BLACK);
            g.fill(new Ellipse2D.Double(ex + Math.cos(ang) * r * 0.08 - r * 0.1,
                    ey + Math.sin(ang) * r * 0.08 - r * 0.1, r * 0.2, r * 0.2));
        }

        g.setFont(new Font("SansSerif", Font.BOLD, 13));
        String label = a.name + " (" + a.type.label + ")";
        int w = g.getFontMetrics().stringWidth(label);
        g.setColor(a.isPlayer ? Color.WHITE : new Color(255, 255, 255, 200));
        g.drawString(label, (int) (a.x - w / 2.0), (int) (a.y - r - 8));
    }

    private void drawHud(Graphics2D g, int cw, int ch) {
        Animal p = world.player;

        // leaderboard
        List<Animal> top = new ArrayList<>(world.animals);
        top.sort((a, b) -> Double.compare(b.xp, a.xp));
        g.setColor(new Color(0, 0, 0, 110));
        g.fillRoundRect(cw - 210, 10, 200, 130, 12, 12);
        g.setColor(Color.WHITE);
        g.setFont(new Font("SansSerif", Font.BOLD, 14));
        g.drawString("Leaderboard", cw - 200, 30);
        g.setFont(new Font("SansSerif", Font.PLAIN, 13));
        for (int i = 0; i < Math.min(5, top.size()); i++) {
            Animal a = top.get(i);
            g.setColor(a == p ? Color.YELLOW : Color.WHITE);
            g.drawString((i + 1) + ". " + a.name + "  " + (int) a.xp, cw - 200, 52 + i * 18);
        }

        // xp + stamina bars
        AnimalType n = p.type.next();
        double prog = n == null ? 1 : (p.xp - p.type.minXp) / (n.minXp - p.type.minXp);
        bar(g, 20, ch - 50, 260, 16, prog, new Color(240, 200, 40),
                "XP " + (int) p.xp + (n == null ? " (max)" : " / " + (int) n.minXp));
        bar(g, 20, ch - 28, 260, 12, p.stamina / 100.0, new Color(80, 200, 255), "Stamina");

        if (world.messageTicks > 0) {
            g.setFont(new Font("SansSerif", Font.BOLD, 22));
            int w = g.getFontMetrics().stringWidth(world.message);
            g.setColor(new Color(0, 0, 0, 150));
            g.drawString(world.message, (cw - w) / 2 + 2, 62);
            g.setColor(Color.WHITE);
            g.drawString(world.message, (cw - w) / 2, 60);
        }

        if (!p.alive) {
            g.setColor(new Color(0, 0, 0, 150));
            g.fillRect(0, 0, cw, ch);
            g.setColor(Color.WHITE);
            g.setFont(new Font("SansSerif", Font.BOLD, 40));
            String s = "You were eaten!";
            g.drawString(s, (cw - g.getFontMetrics().stringWidth(s)) / 2, ch / 2 - 10);
            g.setFont(new Font("SansSerif", Font.PLAIN, 20));
            s = "Final XP: " + (int) p.xp + "  -  click or press ENTER to play again";
            g.drawString(s, (cw - g.getFontMetrics().stringWidth(s)) / 2, ch / 2 + 30);
        }
    }

    private void bar(Graphics2D g, int x, int y, int w, int h, double frac, Color c, String text) {
        g.setColor(new Color(0, 0, 0, 120));
        g.fillRoundRect(x, y, w, h, h, h);
        g.setColor(c);
        g.fillRoundRect(x, y, (int) (w * Math.max(0, Math.min(1, frac))), h, h, h);
        g.setColor(Color.WHITE);
        g.setFont(new Font("SansSerif", Font.BOLD, Math.max(10, h - 4)));
        g.drawString(text, x + 8, y + h - 3);
    }
}
'''


def write_project(out: Path) -> None:
    for rel, content in FILES.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if rel.endswith(".sh"):
            path.chmod(0o755)
    print(f"Project written to {out.resolve()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a mope.io-style Java game project.")
    ap.add_argument("output", nargs="?", default="mope-java", help="output directory (default: mope-java)")
    ap.add_argument("--build", action="store_true", help="compile with javac after generating")
    ap.add_argument("--run", action="store_true", help="build and launch the game")
    args = ap.parse_args()

    out = Path(args.output)
    write_project(out)
    if args.build or args.run:
        subprocess.run([str(out / "build.sh")], check=True)
    if args.run:
        subprocess.run([str(out / "run.sh")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
