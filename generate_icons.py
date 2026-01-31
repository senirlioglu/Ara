from PIL import Image, ImageDraw

def create_icon():
    # Canvas setup
    size = 512
    bg_color = "#667eea"
    fg_color = "white"

    img = Image.new('RGB', (size, size), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Modern Product Search Icon Design
    # 1. The Box (Product)
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

    # Handle
    handle_offset = 60
    handle_length = 80
    handle_width = 30

    start_x = glass_center_x + handle_offset
    start_y = glass_center_y + handle_offset
    end_x = start_x + handle_length
    end_y = start_y + handle_length

    # We want the glass to appear "in front".
    # Mask area behind glass
    mask_radius = glass_radius + 15
    mask_bbox = [glass_center_x - mask_radius, glass_center_y - mask_radius,
                 glass_center_x + mask_radius, glass_center_y + mask_radius]

    # Erase box where glass will be
    draw.ellipse(mask_bbox, fill=bg_color)

    # Erase handle path
    draw.line([start_x, start_y, end_x, end_y], fill=bg_color, width=handle_width + 20)

    # 3. Draw Glass & Handle
    draw.line([start_x, start_y, end_x, end_y], fill=fg_color, width=handle_width)

    # Circle
    glass_bbox = [glass_center_x - glass_radius, glass_center_y - glass_radius,
                  glass_center_x + glass_radius, glass_center_y + glass_radius]
    draw.ellipse(glass_bbox, outline=fg_color, width=30)

    # Save 512
    img.save("static/icon-512.png")

    # Resize and Save 192
    img_small = img.resize((192, 192), Image.Resampling.LANCZOS)
    img_small.save("static/icon-192.png")

    print("Icons generated successfully.")

if __name__ == "__main__":
    create_icon()
