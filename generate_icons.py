from PIL import Image, ImageDraw
import os

def create_gradient(width, height, start_color, end_color):
    base = Image.new('RGB', (width, height), start_color)
    top = Image.new('RGB', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        for x in range(width):
            # Diagonal gradient
            p = (x + y) / (width + height)
            mask_data.append(int(255 * p))
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def draw_search_icon(img):
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Coordinates logic
    center_x, center_y = w // 2, h // 2

    # Circle (Glass)
    radius = int(min(w, h) * 0.25)
    circle_width = int(min(w, h) * 0.08)

    # Handle
    handle_length = int(min(w, h) * 0.25)
    handle_width = int(min(w, h) * 0.08)

    # Draw Circle
    # Offset slightly to top-left to make room for handle
    offset = int(min(w, h) * 0.05)
    cx = center_x - offset
    cy = center_y - offset

    x1, y1 = cx - radius, cy - radius
    x2, y2 = cx + radius, cy + radius

    draw.ellipse([x1, y1, x2, y2], outline='white', width=circle_width)

    # Draw Handle
    # Calculate start point on circle (at 45 degrees / bottom-right)
    # 45 deg = pi/4. cos(45)=sin(45) ~ 0.707
    start_x = cx + int(radius * 0.707)
    start_y = cy + int(radius * 0.707)

    end_x = start_x + handle_length
    end_y = start_y + handle_length

    draw.line([start_x, start_y, end_x, end_y], fill='white', width=handle_width)

    # Make ends of handle rounded (simulate stroke cap)
    # Simple way: draw a circle at end
    r_handle = handle_width // 2
    draw.ellipse([end_x - r_handle, end_y - r_handle, end_x + r_handle, end_y + r_handle], fill='white')
    draw.ellipse([start_x - r_handle, start_y - r_handle, start_x + r_handle, start_y + r_handle], fill='white')

    return img

def generate_icon(size, filename):
    # Colors
    c1 = (102, 126, 234) # #667eea
    c2 = (118, 75, 162)  # #764ba2

    img = create_gradient(size, size, c1, c2)
    img = draw_search_icon(img)

    # Ensure static dir exists
    if not os.path.exists('static'):
        os.makedirs('static')

    path = os.path.join('static', filename)
    img.save(path)
    print(f"Generated {path}")

if __name__ == "__main__":
    generate_icon(192, "icon-192.png")
    generate_icon(512, "icon-512.png")
    generate_icon(180, "apple-touch-icon.png")
