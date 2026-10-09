import { ComponentFixture, TestBed } from '@angular/core/testing';

import { RegisterStepTwoComponent } from './register-step-two.component';

describe('RegisterStepTwoComponent', () => {
  let component: RegisterStepTwoComponent;
  let fixture: ComponentFixture<RegisterStepTwoComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RegisterStepTwoComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(RegisterStepTwoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
