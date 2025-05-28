import random
from products.models import Product

OCCASION_TAGS = [
    'casual', 'party', 'formal', 'wedding', 'beach', 'university', 'sports',
    'picnic', 'date night', 'brunch', 'family gathering', 'holiday', 'interview',
    'girls night', 'gym', 'workout', 'lounging'
]

LOCATION_TAGS = [
    'indoor', 'outdoor', 'office', 'home', 'resort', 'mountains', 'urban',
    'garden', 'seaside', 'mall', 'gym', 'restaurant', 'campus', 'studio'
]

SEASONAL_TAGS = [
    'summer', 'winter', 'spring', 'autumn', 'monsoon', 'all-season',
    'humid', 'dry', 'transitional weather', 'cold evenings'
]

DESCRIPTIONS = [
    "Effortlessly elegant, perfect for casual days or dressy nights.",
    "Lightweight, breathable, and ultra-soft on the skin.",
    "Flattering silhouette that enhances your curves.",
    "Designed with modern women in mind — versatile and trendy.",
    "Crafted from premium fabrics for day-to-night comfort.",
    "Style meets sophistication in this must-have outfit.",
    "Make a statement with bold colors and graceful cuts.",
    "Perfect fusion of tradition and modernity.",
    "Tailored fit for confident, everyday wear.",
    "Drape yourself in comfort and charm this season.",
    "Go from office to outing with seamless style.",
    "Unleash your inner diva — this one's a showstopper!"
]

# Mappings for sensible choices
occasion_to_type = {
    'casual': 'Casual',
    'party': 'Social',
    'formal': 'Workwear',
    'wedding': 'Social',
    'gym': 'Casual',
    'interview': 'Workwear',
    'date night': 'Social',
    'lounging': 'Casual',
}

season_to_brand = {
    'winter': 'Bonanza Satrangi',
    'summer': 'Khaadi',
    'monsoon': 'Sapphire',
    'spring': 'Gul Ahmed',
    'autumn': 'Gul Ahmed',
    'all-season': random.choice(['Khaadi', 'Gul Ahmed', 'Sapphire']),
}

body_shape_choices = ['Hourglass', 'Triangle', 'Rectangle', 'Oval']
skin_tone_choices = ['Light', 'Wheatish', 'Tan', 'Brown']

def assign_sensibly():
    products = Product.objects.all()
    
    for product in products:
        occasion = random.choice(OCCASION_TAGS)
        location = random.choice(LOCATION_TAGS)
        season = random.choice(SEASONAL_TAGS)
        description = random.choice(DESCRIPTIONS)
        
        # Sensible mappings
        clothing_type = occasion_to_type.get(occasion, random.choice(['Casual', 'Workwear', 'Social', 'Maternity']))
        brand = season_to_brand.get(season, random.choice(['Khaadi', 'Gul Ahmed', 'Sapphire', 'Bonanza Satrangi']))
        body_shape = random.choice(body_shape_choices)
        skin_tone = random.choice(skin_tone_choices)

        # Update product
        product.occasion_tags = occasion
        product.location_tags = location
        product.seasonal_tags = season
        product.product_description = description
        product.clothing_types = clothing_type
        product.brand = brand
        product.body_shapes = body_shape
        product.skin_tones = skin_tone

        product.save()
        print(f"Updated {product.product_name}")

assign_sensibly()
