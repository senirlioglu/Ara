from PIL import Image, ImageDraw

def create_icon():
    # Canvas setup
    size = 512
    bg_color = "#1e3a5f"
    fg_color = "white"

    img = Image.new('RGB', (size, size), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Modern Product Search Icon Design
    # 1. The Box (Product)
    # Using a rounded rectangle approach manually or just simple lines
    # Box coordinates
    box_x1, box_y1 = 120, 160
    box_x2, box_y2 = 320, 360
    line_width = 24

    # Draw Box outline
    draw.rectangle([box_x1, box_y1, box_x2, box_y2], outline=fg_color, width=line_width)

    # Draw a line across the box (tape)
    draw.line([box_x1, (box_y1+box_y2)//2, box_x2, (box_y1+box_y2)//2], fill=fg_color, width=line_width//2)
    # Draw vertical line (tape)
    draw.line([(box_x1+box_x2)//2, box_y1, (box_x1+box_x2)//2, box_y2], fill=fg_color, width=line_width//2)

    # 2. The Magnifying Glass (Search)
    # Position: Top right, overlapping the box
    glass_center_x, glass_center_y = 350, 160
    glass_radius = 90

    # Draw the handle first so the glass is on top? Or glass on top.
    # Handle
    handle_offset = 60
    handle_length = 80
    handle_width = 30

    start_x = glass_center_x + handle_offset
    start_y = glass_center_y + handle_offset
    end_x = start_x + handle_length
    end_y = start_y + handle_length

    draw.line([start_x, start_y, end_x, end_y], fill=fg_color, width=handle_width)

    # Glass circle (Ring)
    # We draw a thick circle by drawing a filled circle then a smaller inner circle of bg_color
    # Wait, simple outline circle is better
    # Bounding box for ellipse: [x-r, y-r, x+r, y+r]
    glass_bbox = [glass_center_x - glass_radius, glass_center_y - glass_radius,
                  glass_center_x + glass_radius, glass_center_y + glass_radius]

    # To handle thickness cleanly, we can draw a thick outline
    # But ImageDraw.ellipse with width is sometimes jagged. Let's try it.
    draw.ellipse(glass_bbox, outline=fg_color, width=30)

    # Optional: Fill the glass with semi-transparent white?
    # No, keep it minimal (flat design).
    # But the glass lines shouldn't overlap the box lines messily.
    # To make it look "in front", we can draw a "cleanup" circle first (bg_color)
    # slightly larger than the glass ring inner diameter to erase the box behind it.

    # Let's redraw.
    # 1. Draw Box
    # 2. Erase area where Glass will be
    # 3. Draw Glass

    # Re-initialize
    img = Image.new('RGB', (size, size), color=bg_color)
    draw = ImageDraw.Draw(img)

    # 1. Draw Box
    draw.rectangle([box_x1, box_y1, box_x2, box_y2], outline=fg_color, width=line_width)
    # Tape details
    draw.line([box_x1, (box_y1+box_y2)//2, box_x2, (box_y1+box_y2)//2], fill=fg_color, width=line_width//2)
    draw.line([(box_x1+box_x2)//2, box_y1, (box_x1+box_x2)//2, box_y2], fill=fg_color, width=line_width//2)

    # 2. "Erase" background for Glass (to simulate "in front")
    # Mask circle: slightly larger than outer rim of glass?
    # Actually just the glass area including the rim.
    mask_radius = glass_radius + 15 # clearance
    mask_bbox = [glass_center_x - mask_radius, glass_center_y - mask_radius,
                 glass_center_x + mask_radius, glass_center_y + mask_radius]
    draw.ellipse(mask_bbox, fill=bg_color)

    # Mask for handle
    # A thick line in bg color
    draw.line([start_x, start_y, end_x, end_y], fill=bg_color, width=handle_width + 20)

    # 3. Draw Glass & Handle
    # Handle
    draw.line([start_x, start_y, end_x, end_y], fill=fg_color, width=handle_width)

    # Circle
    draw.ellipse(glass_bbox, outline=fg_color, width=30)

    # Save 512
    img.save("static/icon-512.png")

    # Resize and Save 192
    img_small = img.resize((192, 192), Image.Resampling.LANCZOS)
    img_small.save("static/icon-192.png")

    print("Icons generated successfully.")

if __name__ == "__main__":
    create_icon()
