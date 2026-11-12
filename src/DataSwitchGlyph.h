#import <UIKit/UIKit.h>

// Keep source pixels intact; only the compact rendition is enlarged.
// CCSIM reference: 50pt canvas, 35.33pt maximum opaque extent.
static inline UIImage *DataSwitchRenderGlyph(UIImage *source, CGFloat canvas) {
    if (!source || source.size.width<=0 || source.size.height<=0) return nil;
    UIGraphicsImageRendererFormat *format=[UIGraphicsImageRendererFormat preferredFormat];
    format.opaque=NO;
    format.scale=MAX(1.0,UIScreen.mainScreen.scale);
    CGSize size=source.size;
    CGFloat factor=MIN(canvas/size.width,canvas/size.height);
    CGSize fit=CGSizeMake(size.width*factor,size.height*factor);
    UIGraphicsImageRenderer *renderer=[[UIGraphicsImageRenderer alloc] initWithSize:CGSizeMake(canvas,canvas) format:format];
    UIImage *result=[renderer imageWithActions:^(__unused UIGraphicsImageRendererContext *context) {
        [source drawInRect:CGRectMake((canvas-fit.width)*.5,(canvas-fit.height)*.5,fit.width,fit.height)];
    }];
    return [result imageWithRenderingMode:UIImageRenderingModeAlwaysTemplate];
}

static inline UIImage *DataSwitchLoadGlyph(Class owner, BOOL compact) {
    UIImage *source=[UIImage imageNamed:@"DataSwitch" inBundle:[NSBundle bundleForClass:owner] compatibleWithTraitCollection:nil];
    if (!source) source=[UIImage systemImageNamed:@"simcard"];
    return DataSwitchRenderGlyph(source,compact?46.0:32.0);
}
